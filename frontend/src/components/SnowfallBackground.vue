<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";

type Snowflake = {
  x: number;
  y: number;
  radius: number;
  speed: number;
  sway: number;
  phase: number;
  opacity: number;
  rotation: number;
  rotationSpeed: number;
};

const canvas = ref<HTMLCanvasElement | null>(null);

let context: CanvasRenderingContext2D | null = null;
let flakes: Snowflake[] = [];
let animationFrame = 0;
let motionQuery: MediaQueryList | null = null;
let width = 0;
let height = 0;
let pixelRatio = 1;
let previousTime = 0;

function createFlakes() {
  const count = Math.min(112, Math.round((width * height) / 13000));
  flakes = Array.from({ length: count }, () => ({
    x: Math.random() * width,
    y: Math.random() * height,
    radius: 5 + Math.random() * 7,
    speed: 12 + Math.random() * 24,
    sway: 7 + Math.random() * 14,
    phase: Math.random() * Math.PI * 2,
    opacity: 0.5 + Math.random() * 0.42,
    rotation: Math.random() * Math.PI * 2,
    rotationSpeed: (Math.random() - 0.5) * 0.42,
  }));
}

function traceCrystalFlake(flake: Snowflake) {
  if (!context) return;
  const branchStart = flake.radius * 0.54;
  const branchEnd = flake.radius * 0.78;
  const branchWidth = flake.radius * 0.24;

  context.beginPath();
  for (let arm = 0; arm < 6; arm += 1) {
    context.moveTo(0, 0);
    context.lineTo(0, -flake.radius);
    context.moveTo(0, -branchStart);
    context.lineTo(-branchWidth, -branchEnd);
    context.moveTo(0, -branchStart);
    context.lineTo(branchWidth, -branchEnd);
    context.moveTo(0, -flake.radius * 0.76);
    context.lineTo(-branchWidth * 0.62, -flake.radius * 0.94);
    context.moveTo(0, -flake.radius * 0.76);
    context.lineTo(branchWidth * 0.62, -flake.radius * 0.94);
    context.rotate(Math.PI / 3);
  }
}

function drawCrystalFlake(flake: Snowflake) {
  if (!context) return;
  context.save();
  context.translate(flake.x, flake.y);
  context.rotate(flake.rotation);
  context.lineCap = "round";
  context.lineJoin = "round";

  traceCrystalFlake(flake);
  context.lineWidth = Math.max(1.15, flake.radius * 0.14);
  context.shadowBlur = flake.radius * 0.9;
  context.shadowColor = `rgba(55, 139, 246, ${flake.opacity * 0.72})`;
  context.strokeStyle = `rgba(191, 226, 255, ${flake.opacity})`;
  context.stroke();

  traceCrystalFlake(flake);
  context.lineWidth = Math.max(0.55, flake.radius * 0.055);
  context.shadowBlur = flake.radius * 0.35;
  context.shadowColor = `rgba(255, 255, 255, ${flake.opacity})`;
  context.strokeStyle = `rgba(255, 255, 255, ${Math.min(1, flake.opacity + 0.08)})`;
  context.stroke();

  context.beginPath();
  for (let point = 0; point < 6; point += 1) {
    const angle = point * Math.PI / 3 - Math.PI / 2;
    const x = Math.cos(angle) * flake.radius * 0.2;
    const y = Math.sin(angle) * flake.radius * 0.2;
    if (point === 0) context.moveTo(x, y);
    else context.lineTo(x, y);
  }
  context.closePath();
  context.fillStyle = `rgba(235, 248, 255, ${Math.min(1, flake.opacity + 0.08)})`;
  context.fill();
  context.restore();
}

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
  createFlakes();
  draw(performance.now(), false);
}

function draw(time: number, advance = true) {
  if (!context || width === 0 || height === 0) return;
  const elapsedSeconds = previousTime === 0 ? 0 : Math.min(0.06, (time - previousTime) / 1000);
  previousTime = time;

  context.fillStyle = "#a9cff0";
  context.fillRect(0, 0, width, height);

  for (const flake of flakes) {
    if (advance) {
      const motionScale = motionQuery?.matches ? 0.45 : 1;
      flake.y += flake.speed * elapsedSeconds * motionScale;
      flake.x += Math.sin(time * 0.00045 + flake.phase) * flake.sway * elapsedSeconds * motionScale;
      flake.rotation += flake.rotationSpeed * elapsedSeconds * motionScale;
      if (flake.y > height + flake.radius * 2) {
        flake.y = -flake.radius * 2;
        flake.x = Math.random() * width;
      }
      if (flake.x < -8) flake.x = width + 8;
      else if (flake.x > width + 8) flake.x = -8;
    }

    drawCrystalFlake(flake);
  }
  context.shadowBlur = 0;
}

function animate(time: number) {
  draw(time);
  animationFrame = window.requestAnimationFrame(animate);
}

function stopAnimation() {
  if (animationFrame) window.cancelAnimationFrame(animationFrame);
  animationFrame = 0;
}

function startAnimation() {
  stopAnimation();
  previousTime = 0;
  if (document.hidden) {
    draw(performance.now(), false);
    return;
  }
  animationFrame = window.requestAnimationFrame(animate);
}

onMounted(() => {
  context = canvas.value?.getContext("2d", { alpha: false }) ?? null;
  if (!context) return;
  motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  motionQuery.addEventListener("change", startAnimation);
  window.addEventListener("resize", resizeCanvas);
  document.addEventListener("visibilitychange", startAnimation);
  resizeCanvas();
  startAnimation();
});

onUnmounted(() => {
  stopAnimation();
  motionQuery?.removeEventListener("change", startAnimation);
  window.removeEventListener("resize", resizeCanvas);
  document.removeEventListener("visibilitychange", startAnimation);
  flakes = [];
  context = null;
});
</script>

<template>
  <canvas ref="canvas" class="snowfall-background" aria-hidden="true"></canvas>
</template>
