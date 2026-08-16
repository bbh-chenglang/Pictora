<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

const canvas = ref<HTMLCanvasElement | null>(null);

let context: CanvasRenderingContext2D | null = null;
let animationFrame = 0;
let motionQuery: MediaQueryList | null = null;
let width = 0;
let height = 0;
let pixelRatio = 1;
let lastDrawAt = 0;

const pointer = {
  x: window.innerWidth / 2,
  y: window.innerHeight / 2,
  targetX: window.innerWidth / 2,
  targetY: window.innerHeight / 2,
  strength: 0,
  targetStrength: 0,
};

function resizeCanvas() {
  if (!canvas.value || !context) return;
  width = window.innerWidth;
  height = window.innerHeight;
  pixelRatio = Math.min(window.devicePixelRatio || 1, 1.5);
  canvas.value.width = Math.round(width * pixelRatio);
  canvas.value.height = Math.round(height * pixelRatio);
  canvas.value.style.width = `${width}px`;
  canvas.value.style.height = `${height}px`;
  context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  draw(performance.now());
}

function warpedPoint(x: number, y: number, time: number) {
  let offsetX = Math.sin(y * 0.008 + time * 0.0001) * 1.4;
  let offsetY = Math.sin(x * 0.007 - time * 0.00008) * 1.1;
  const distanceX = x - pointer.x;
  const distanceY = y - pointer.y;
  const distance = Math.hypot(distanceX, distanceY);
  const radius = Math.min(320, Math.max(260, Math.min(width, height) * 0.34));

  if (pointer.strength > 0.002 && distance < radius) {
    const edgeDistance = 1 - distance / radius;
    const depth = Math.sin(edgeDistance * Math.PI / 2) ** 2;
    const perspectivePull = depth * pointer.strength * 0.24;
    offsetX -= distanceX * perspectivePull;
    offsetY -= distanceY * perspectivePull;
  }

  return { x: x + offsetX, y: y + offsetY };
}

function strokeGridLine(
  start: number,
  end: number,
  fixed: number,
  vertical: boolean,
  time: number,
  major: boolean,
) {
  if (!context) return;
  context.beginPath();
  const sampleStep = 18;
  for (let position = start; position <= end + sampleStep; position += sampleStep) {
    const point = vertical
      ? warpedPoint(fixed, Math.min(position, end), time)
      : warpedPoint(Math.min(position, end), fixed, time);
    if (position === start) context.moveTo(point.x, point.y);
    else context.lineTo(point.x, point.y);
  }
  context.strokeStyle = major ? "rgba(59, 130, 246, 0.15)" : "rgba(161, 161, 170, 0.09)";
  context.lineWidth = major ? 1.5 : 1.05;
  context.stroke();
}

function draw(time: number) {
  if (!context || width === 0 || height === 0) return;
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#0b0b0e";
  context.fillRect(0, 0, width, height);

  pointer.x += (pointer.targetX - pointer.x) * 0.13;
  pointer.y += (pointer.targetY - pointer.y) * 0.13;
  pointer.strength += (pointer.targetStrength - pointer.strength) * 0.085;
  const flowTime = motionQuery?.matches ? 0 : time;
  const spacing = 72;
  const totalDriftX = flowTime * 0.0007;
  const totalDriftY = flowTime * 0.0005;
  const driftX = totalDriftX % spacing;
  const driftY = totalDriftY % spacing;
  const horizontalCycle = Math.floor(totalDriftX / spacing);
  const verticalCycle = Math.floor(totalDriftY / spacing);

  let lineIndex = -1;
  for (let x = driftX - spacing; x <= width + spacing; x += spacing) {
    strokeGridLine(-24, height + 24, x, true, flowTime, (lineIndex - horizontalCycle) % 5 === 0);
    lineIndex += 1;
  }

  lineIndex = -1;
  for (let y = driftY - spacing; y <= height + spacing; y += spacing) {
    strokeGridLine(-24, width + 24, y, false, flowTime, (lineIndex - verticalCycle) % 5 === 0);
    lineIndex += 1;
  }
}

function animate(time: number) {
  const frameInterval = 32;
  if (time - lastDrawAt >= frameInterval) {
    draw(time);
    lastDrawAt = time;
  }
  animationFrame = window.requestAnimationFrame(animate);
}

function stopAnimation() {
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
}

function startAnimation() {
  stopAnimation();
  if (document.hidden) {
    draw(performance.now());
    return;
  }
  lastDrawAt = 0;
  animationFrame = window.requestAnimationFrame(animate);
}

function handlePointerMove(event: PointerEvent) {
  updatePointerPosition(event.clientX, event.clientY);
}

function handleMouseMove(event: MouseEvent) {
  updatePointerPosition(event.clientX, event.clientY);
}

function updatePointerPosition(clientX: number, clientY: number) {
  if (pointer.targetStrength === 0 && pointer.strength < 0.02) {
    pointer.x = clientX;
    pointer.y = clientY;
  }
  pointer.targetX = clientX;
  pointer.targetY = clientY;
  pointer.targetStrength = 1;
}

function handlePointerLeave() {
  pointer.targetStrength = 0;
}

function handleVisibilityChange() {
  startAnimation();
}

onMounted(() => {
  context = canvas.value?.getContext("2d", { alpha: false }) ?? null;
  if (!context) return;
  motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  motionQuery.addEventListener("change", startAnimation);
  window.addEventListener("resize", resizeCanvas);
  window.addEventListener("pointermove", handlePointerMove, { passive: true });
  window.addEventListener("mousemove", handleMouseMove, { passive: true });
  document.documentElement.addEventListener("pointerleave", handlePointerLeave);
  document.addEventListener("visibilitychange", handleVisibilityChange);
  resizeCanvas();
  startAnimation();
});

onUnmounted(() => {
  stopAnimation();
  motionQuery?.removeEventListener("change", startAnimation);
  window.removeEventListener("resize", resizeCanvas);
  window.removeEventListener("pointermove", handlePointerMove);
  window.removeEventListener("mousemove", handleMouseMove);
  document.documentElement.removeEventListener("pointerleave", handlePointerLeave);
  document.removeEventListener("visibilitychange", handleVisibilityChange);
  context = null;
});
</script>

<template>
  <canvas ref="canvas" class="flowing-grid-background" aria-hidden="true"></canvas>
</template>
