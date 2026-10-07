"""Separate legacy image/video projects without deleting any tasks or history."""
import aiosqlite


async def migrate_project_types(connection: aiosqlite.Connection) -> None:
    columns = {row[1] for row in await (await connection.execute("PRAGMA table_info(projects)")).fetchall()}
    if "media_type" in columns:
        return
    sequence = await (await connection.execute("SELECT seq FROM sqlite_sequence WHERE name='projects'")).fetchone()
    # The caller disables FK enforcement for the standard SQLite table rebuild.
    await connection.execute("""
        CREATE TABLE projects_typed (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            media_type TEXT NOT NULL DEFAULT 'image' CHECK(media_type IN ('image','video')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, media_type, name)
        )
    """)
    await connection.execute("""
        INSERT INTO projects_typed(id,user_id,name,created_at,updated_at)
        SELECT id,user_id,name,created_at,updated_at FROM projects
    """)
    await connection.execute("DROP TABLE projects")
    await connection.execute("ALTER TABLE projects_typed RENAME TO projects")
    if sequence:
        await connection.execute("UPDATE sqlite_sequence SET seq=MAX(seq,?) WHERE name='projects'", (sequence[0],))
    await connection.execute("CREATE INDEX idx_projects_user_updated ON projects(user_id, updated_at DESC, id DESC)")
    rows = await (await connection.execute("""
        SELECT id,user_id,name,created_at,updated_at FROM projects
        WHERE EXISTS(SELECT 1 FROM video_tasks WHERE project_id=projects.id)
    """)).fetchall()
    for project_id, user_id, name, created_at, updated_at in rows:
        has_images = await (await connection.execute(
            "SELECT 1 FROM history WHERE project_id=? LIMIT 1", (project_id,)
        )).fetchone()
        if not has_images:
            await connection.execute("UPDATE projects SET media_type='video' WHERE id=?", (project_id,))
        else:
            cursor = await connection.execute(
                "INSERT INTO projects(user_id,name,media_type,created_at,updated_at) VALUES(?,?,'video',?,?)",
                (user_id, name, created_at, updated_at),
            )
            await connection.execute("UPDATE video_tasks SET project_id=? WHERE project_id=?", (cursor.lastrowid, project_id))
    # A video-only legacy default must not leave image generation without a project.
    users_table = await (await connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='users'")).fetchone()
    if not users_table:
        return
    await connection.execute("""
        INSERT INTO projects(user_id,name,media_type)
        SELECT id,'第一个项目','image' FROM users
        WHERE NOT EXISTS(SELECT 1 FROM projects WHERE user_id=users.id AND media_type='image')
    """)
