const canvas = document.getElementById("starfield");
const ctx = canvas.getContext("2d");

const stars = [];
const shooting = [];
const STAR_COUNT = 190;

function resize() {
  canvas.width = window.innerWidth;
  canvas.height = window.innerHeight;
}

function createStars() {
  stars.length = 0;
  for (let i = 0; i < STAR_COUNT; i += 1) {
    stars.push({
      x: Math.random() * canvas.width,
      y: Math.random() * canvas.height,
      r: Math.random() * 1.7 + 0.2,
      a: Math.random() * 0.8 + 0.2,
      drift: Math.random() * 0.3 + 0.05,
    });
  }
}

function spawnShootingStar() {
  shooting.push({
    x: Math.random() * canvas.width * 0.7 + canvas.width * 0.15,
    y: Math.random() * canvas.height * 0.25,
    vx: -(Math.random() * 8 + 8),
    vy: Math.random() * 2 + 2,
    life: 1,
  });
}

function draw() {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  for (const s of stars) {
    s.y += s.drift;
    if (s.y > canvas.height + 2) {
      s.y = -2;
      s.x = Math.random() * canvas.width;
    }
    ctx.beginPath();
    ctx.fillStyle = `rgba(190,220,255,${s.a})`;
    ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2);
    ctx.fill();
  }

  for (let i = shooting.length - 1; i >= 0; i -= 1) {
    const p = shooting[i];
    p.x += p.vx;
    p.y += p.vy;
    p.life -= 0.012;

    ctx.beginPath();
    ctx.strokeStyle = `rgba(255,240,200,${Math.max(0, p.life)})`;
    ctx.lineWidth = 1.4;
    ctx.moveTo(p.x, p.y);
    ctx.lineTo(p.x - p.vx * 2.7, p.y - p.vy * 2.7);
    ctx.stroke();

    if (p.life <= 0) shooting.splice(i, 1);
  }

  requestAnimationFrame(draw);
}

window.addEventListener("resize", () => {
  resize();
  createStars();
});

setInterval(() => {
  if (Math.random() < 0.6) spawnShootingStar();
}, 2400);

resize();
createStars();
draw();
