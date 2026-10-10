import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
import aiosqlite
from app.video.schemas import ACTIVE_STATUSES, TRACKED_STATUSES

class VideoError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        self.code, self.message, self.status = code, message, status
        super().__init__(message)

class VideoRepository:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    @asynccontextmanager
    async def connect(self):
        db = aiosqlite.connect(self.database_path)
        opening = asyncio.ensure_future(db)
        try:
            await asyncio.shield(opening)
        except asyncio.CancelledError:
            # Opening SQLite runs on its own thread; cancellation must not leave
            # that thread posting results to an event loop that has exited.
            await opening
            await db.close()
            await asyncio.to_thread(db.join)
            raise
        try:
            db.row_factory = aiosqlite.Row
            await db.execute("PRAGMA foreign_keys=ON")
            await db.execute("PRAGMA busy_timeout=5000")
            yield db
        finally:
            async def close():
                await db.close()
                await asyncio.to_thread(db.join)
            closing = asyncio.create_task(close())
            try:
                await asyncio.shield(closing)
            except asyncio.CancelledError:
                await closing
                raise

    async def rows(self, sql, args=()):
        async with self.connect() as db:
            return [dict(r) for r in await (await db.execute(sql, args)).fetchall()]

    async def execute(self, sql, args=()):
        async with self.connect() as db:
            cur = await db.execute(sql, args)
            await db.commit()
            return cur.lastrowid

    async def get_key(self, user_id, config_id):
        rows=await self.rows("SELECT * FROM video_api_key_configs WHERE user_id=? AND id=?",(user_id,config_id))
        if not rows:
            raise VideoError("video_key_not_found","视频 Key 配置不存在",404)
        return rows[0]

    async def list_keys(self,user_id):
        rows=await self.rows("SELECT * FROM video_api_key_configs WHERE user_id=? ORDER BY id",(user_id,))
        active=await self.rows("SELECT active_config_id FROM video_preferences WHERE user_id=?",(user_id,))
        return {"configs":[{k:v for k,v in r.items() if k!='api_key'}|{'api_key_configured':bool(r['api_key'])} for r in rows],"active_config_id":active[0]['active_config_id'] if active else (rows[0]['id'] if rows else None)}

    async def assert_key_idle(self,db,user_id,config_id):
        marks=','.join('?' for _ in TRACKED_STATUSES)
        row=await (await db.execute(f"SELECT 1 FROM video_tasks WHERE user_id=? AND api_key_config_id=? AND tracking_abandoned=0 AND status IN ({marks}) LIMIT 1",(user_id,config_id,*TRACKED_STATUSES))).fetchone()
        if row:
            raise VideoError('video_key_busy','此 Key 仍有追踪中的视频，请完成或明确放弃追踪后再操作',409)

    async def save_key(self,user_id,alias,api_key,model,config_id=None):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                if config_id is None:
                    cur=await db.execute("INSERT INTO video_api_key_configs(user_id,alias,api_key,model) VALUES(?,?,?,?)",(user_id,alias,api_key,model))
                    config_id=cur.lastrowid
                    await db.execute("INSERT OR IGNORE INTO video_preferences(user_id,active_config_id) VALUES(?,?)",(user_id,config_id))
                else:
                    current=await (await db.execute("SELECT * FROM video_api_key_configs WHERE user_id=? AND id=?",(user_id,config_id))).fetchone()
                    if not current:
                        raise VideoError('video_key_not_found','视频配置不存在',404)
                    if api_key and api_key!=current['api_key']:
                        await self.assert_key_idle(db,user_id,config_id)
                    await db.execute("UPDATE video_api_key_configs SET alias=?,api_key=?,model=?,updated_at=CURRENT_TIMESTAMP WHERE user_id=? AND id=?",(alias,api_key or current['api_key'],model,user_id,config_id))
                await db.commit()
            except aiosqlite.IntegrityError:
                raise VideoError('video_key_alias_taken','视频配置名称已存在',409) from None
        return next(k for k in (await self.list_keys(user_id))['configs'] if k['id']==config_id)

    async def delete_key(self,user_id,config_id):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            await self.assert_key_idle(db,user_id,config_id)
            cur=await db.execute("DELETE FROM video_api_key_configs WHERE user_id=? AND id=?",(user_id,config_id))
            if not cur.rowcount:
                raise VideoError('video_key_not_found','视频配置不存在',404)
            await db.execute("UPDATE video_preferences SET active_config_id=(SELECT MIN(id) FROM video_api_key_configs WHERE user_id=?) WHERE user_id=? AND active_config_id IS NULL",(user_id,user_id))
            await db.commit()

    async def activate_key(self,user_id,config_id):
        await self.get_key(user_id,config_id)
        await self.execute("INSERT INTO video_preferences(user_id,active_config_id) VALUES(?,?) ON CONFLICT(user_id) DO UPDATE SET active_config_id=excluded.active_config_id",(user_id,config_id))

    async def add_asset(self,asset):
        fields=tuple(asset)
        await self.execute(f"INSERT INTO video_assets({','.join(fields)}) VALUES({','.join('?' for _ in fields)})",tuple(asset.values()))
        return asset

    async def get_asset(self,asset_id,user_id=None):
        sql='SELECT * FROM video_assets WHERE id=?'
        args=(asset_id,)
        if user_id is not None:
            sql+=' AND user_id=?'
            args+=(user_id,)
        rows=await self.rows(sql,args)
        if not rows:
            raise VideoError('video_asset_not_found','素材不存在',404)
        return rows[0]

    async def get_task(self,user_id,task_id,public=False):
        rows=await self.rows('SELECT * FROM video_tasks WHERE user_id=? AND id=?',(user_id,task_id))
        if not rows:
            raise VideoError('video_task_not_found','视频任务不存在',404)
        task=rows[0]
        task['results']=await self.rows('SELECT * FROM video_results WHERE task_id=? ORDER BY position',(task_id,))
        return self.public_task(task) if public else task

    @staticmethod
    def public_task(task):
        task=dict(task)
        request=json.loads(task.pop('request_json'))
        task.pop('payload_json',None)
        task['materials']=request.get('materials',[])
        task['results']=[dict(r) for r in task.get('results',[])]
        for result in task['results']:
            result.pop('object_key',None)
            base=f"/api/videos/tasks/{task['id']}/results/{result['id']}"
            result['play_url']=base+'/play'
            result['download_url']=base+'/download'
        return task

    async def existing_request(self,user_id,request_id,request_json):
        rows=await self.rows('SELECT id,request_json FROM video_tasks WHERE user_id=? AND request_id=?',(user_id,str(request_id)))
        if not rows:
            closed=await self.rows('SELECT 1 FROM video_closed_requests WHERE user_id=? AND request_id=?',(user_id,str(request_id)))
            if closed:
                raise VideoError('video_request_closed','旧请求已关闭，请使用新的请求编号提交',410)
            return None
        if rows[0]['request_json']!=request_json:
            raise VideoError('video_request_conflict','同一个请求 ID 不能用于不同参数',409)
        return await self.get_task(user_id,rows[0]['id'],public=True)

    async def lookup_request(self,user_id,request_id):
        rows=await self.rows('SELECT id FROM video_tasks WHERE user_id=? AND request_id=?',(user_id,str(request_id)))
        if rows:
            return {'state':'accepted','task':await self.get_task(user_id,rows[0]['id'],public=True)}
        closed=await self.rows('SELECT 1 FROM video_closed_requests WHERE user_id=? AND request_id=?',(user_id,str(request_id)))
        return {'state':'closed' if closed else 'missing','task':None}

    async def resolve_request(self,user_id,request_id,project_id):
        async with self.connect() as db:
            # Serialize resolution with create_task. Either creation wins and
            # we return that task, or closure wins and every delayed POST fails.
            await db.execute('BEGIN IMMEDIATE')
            project=await (await db.execute("SELECT 1 FROM projects WHERE id=? AND user_id=? AND media_type='video'",(project_id,user_id))).fetchone()
            if not project:
                raise VideoError('project_not_found','项目不存在',404)
            task=await (await db.execute('SELECT id,project_id FROM video_tasks WHERE user_id=? AND request_id=?',(user_id,str(request_id)))).fetchone()
            if task and task['project_id']!=project_id:
                raise VideoError('video_request_conflict','该请求属于其他项目',409)
            if not task:
                await db.execute('INSERT OR IGNORE INTO video_closed_requests(user_id,request_id) VALUES(?,?)',(user_id,str(request_id)))
            await db.commit()
        if task:
            return {'state':'accepted','task':await self.get_task(user_id,task['id'],public=True)}
        return {'state':'closed','task':None}

    async def check_capacity(self,db,user_id,settings):
        marks=','.join('?' for _ in ACTIVE_STATUSES)
        row=await (await db.execute(f"SELECT COUNT(*),SUM(CASE WHEN user_id=? THEN 1 ELSE 0 END) FROM video_tasks WHERE status IN ({marks}) AND tracking_abandoned=0",(user_id,*ACTIVE_STATUSES))).fetchone()
        if row[0]>=settings.video_max_active_tasks or (row[1] or 0)>=settings.video_max_tasks_per_user:
            raise VideoError('video_capacity','视频任务数量已达到上限',429)

    async def create_task(self,user_id,request,request_json,payload,asset_ids,settings):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            old=await (await db.execute('SELECT id,request_json FROM video_tasks WHERE user_id=? AND request_id=?',(user_id,str(request.request_id)))).fetchone()
            if old:
                if old['request_json']!=request_json:
                    raise VideoError('video_request_conflict','请求 ID 已用于不同参数',409)
                return old['id'],False
            closed=await (await db.execute('SELECT 1 FROM video_closed_requests WHERE user_id=? AND request_id=?',(user_id,str(request.request_id)))).fetchone()
            if closed:
                raise VideoError('video_request_closed','旧请求已关闭，请使用新的请求编号提交',410)
            for table,value in (('projects',request.project_id),('video_api_key_configs',request.api_key_config_id)):
                scope=" AND media_type='video'" if table=='projects' else ''
                row=await (await db.execute(f'SELECT 1 FROM {table} WHERE id=? AND user_id=?'+scope,(value,user_id))).fetchone()
                if not row:
                    raise VideoError('video_owner_mismatch','项目或视频配置不存在',404)
            await self.check_capacity(db,user_id,settings)
            for asset_id in set(asset_ids):
                owned=await (await db.execute('SELECT 1 FROM video_assets WHERE id=? AND user_id=?',(asset_id,user_id))).fetchone()
                if not owned:
                    raise VideoError('video_asset_not_found','素材不存在',404)
            cur=await db.execute('INSERT INTO video_tasks(user_id,project_id,api_key_config_id,request_id,request_json,payload_json,model,prompt,duration,resolution,ratio) VALUES(?,?,?,?,?,?,?,?,?,?,?)',(user_id,request.project_id,request.api_key_config_id,str(request.request_id),request_json,json.dumps(payload,ensure_ascii=False),request.model,request.prompt,payload['duration'],payload['resolution'],payload['ratio']))
            task_id=cur.lastrowid
            for asset_id in set(asset_ids):
                await db.execute('INSERT INTO video_task_assets(task_id,asset_id) VALUES(?,?)',(task_id,asset_id))
                await db.execute('UPDATE video_assets SET ever_referenced=1 WHERE id=?',(asset_id,))
            await db.execute('UPDATE projects SET updated_at=CURRENT_TIMESTAMP WHERE id=?',(request.project_id,))
            await db.commit()
        return task_id,True

    async def prepare_resume(self,user_id,task_id,settings):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            row=await (await db.execute('SELECT * FROM video_tasks WHERE user_id=? AND id=?',(user_id,task_id))).fetchone()
            if not row:
                raise VideoError('video_task_not_found','视频任务不存在',404)
            if row['status'] in ACTIVE_STATUSES:
                return False
            if row['status'] not in ('polling_paused','storage_failed','abandoned') or not row['upstream_task_id']:
                raise VideoError('video_cannot_resume','此任务无法恢复查询或保存',409)
            await self.check_capacity(db,user_id,settings)
            await db.execute("UPDATE video_tasks SET status='running',tracking_abandoned=0,error_code=NULL,error_message=NULL WHERE id=?",(task_id,))
            await db.commit()
        return True

    async def bind_task(self,user_id,task_id,upstream_id):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            try:
                cur=await db.execute("UPDATE video_tasks SET upstream_task_id=?,status='polling_paused',tracking_abandoned=0,updated_at=CURRENT_TIMESTAMP WHERE id=? AND user_id=? AND upstream_task_id IS NULL AND status IN ('submission_unknown','abandoned')",(upstream_id,task_id,user_id))
                if not cur.rowcount:
                    raise VideoError('video_bind_invalid','任务已被修改或接管，请刷新后再试',409)
                await db.commit()
            except aiosqlite.IntegrityError:
                raise VideoError('video_bind_duplicate','此上游任务已被接管',409) from None

    async def update_task(self,task_id,**fields):
        allowed={'status','upstream_task_id','upstream_status','progress','error_code','error_message','started_at','completed_at','tracking_abandoned'}
        if not fields or not set(fields)<=allowed:
            raise ValueError('Invalid task update')
        assignments=','.join(f'{key}=?' for key in fields)
        await self.execute(f'UPDATE video_tasks SET {assignments},updated_at=CURRENT_TIMESTAMP WHERE id=?',(*fields.values(),task_id))

    async def claim_submission(self,task_id):
        async with self.connect() as db:
            cur=await db.execute("UPDATE video_tasks SET status='submitting',started_at=CURRENT_TIMESTAMP WHERE id=? AND status='queued' AND upstream_task_id IS NULL AND tracking_abandoned=0",(task_id,))
            await db.commit()
            return bool(cur.rowcount)

    async def result_for_position(self,task_id,position,object_key):
        await self.execute('INSERT OR IGNORE INTO video_results(task_id,position,object_key,filename) VALUES(?,?,?,?)',(task_id,position,object_key,f'pictora-{task_id}-{position+1}.mp4'))
        return (await self.rows('SELECT * FROM video_results WHERE task_id=? AND position=?',(task_id,position)))[0]

    async def mark_result_stored(self,result_id,size,duration):
        await self.execute('UPDATE video_results SET stored=1,byte_size=?,duration_seconds=? WHERE id=?',(size,duration,result_id))

    async def delete_task(self,user_id,task_id):
        async with self.connect() as db:
            await db.execute('BEGIN IMMEDIATE')
            row=await (await db.execute('SELECT * FROM video_tasks WHERE user_id=? AND id=?',(user_id,task_id))).fetchone()
            if not row:
                raise VideoError('video_task_not_found','视频任务不存在',404)
            if not row['tracking_abandoned'] and row['status'] in TRACKED_STATUSES:
                raise VideoError('video_task_tracking','请先完成或明确放弃追踪。删除不会取消上游任务或退款。',409)
            await db.execute('DELETE FROM video_tasks WHERE id=?',(task_id,))
            await db.commit()

    async def list_tasks(self,user_id,project_id=None,*,limit=100,offset=0):
        args=(user_id,)
        sql='SELECT * FROM video_tasks WHERE user_id=?'
        if project_id is not None:
            sql+=' AND project_id=?'
            args+=(project_id,)
        tasks=await self.rows(sql+' ORDER BY created_at DESC,id DESC LIMIT ? OFFSET ?',(*args,limit,offset))
        results=await self.rows('SELECT r.* FROM video_results r JOIN video_tasks t ON t.id=r.task_id WHERE t.user_id=?',(user_id,))
        grouped={}
        for result in results:
            grouped.setdefault(result['task_id'],[]).append(result)
        return [self.public_task(t|{'results':grouped.get(t['id'],[])}) for t in tasks]
