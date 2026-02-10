// Canvas setup
const starCanvas = document.getElementById("starfield");
const nebulaCanvas = document.getElementById("nebula");
const starCtx = starCanvas.getContext("2d");
const nebulaCtx = nebulaCanvas.getContext("2d");

// State
const stars = [];
const shooting = [];
const particles = [];
const nebulaClouds = [];
const STAR_COUNT = 250;
const PARTICLE_COUNT = 40;
const NEBULA_COUNT = 8;

let mouseX = window.innerWidth / 2;
let mouseY = window.innerHeight / 2;
let scrollY = 0;

// Resize handler
function resize() {
  starCanvas.width = window.innerWidth;
  starCanvas.height = window.innerHeight;
  nebulaCanvas.width = window.innerWidth;
  nebulaCanvas.height = window.innerHeight;
}

// Create stars with parallax layers
function createStars() {
  stars.length = 0;
  for (let i = 0; i < STAR_COUNT; i += 1) {
    const layer = Math.random();
    stars.push({
      x: Math.random() * starCanvas.width,
      y: Math.random() * starCanvas.height,
      r: Math.random() * 1.8 + 0.3,
      a: Math.random() * 0.8 + 0.3,
      drift: Math.random() * 0.4 + 0.05,
      layer: layer,
      twinkle: Math.random() * Math.PI * 2,
      twinkleSpeed: Math.random() * 0.02 + 0.01,
    });
  }
}

// Create orbital particles (Venus-inspired)
function createParticles() {
  particles.length = 0;
  const centerX = starCanvas.width / 2;
  const centerY = starCanvas.height / 2;

  for (let i = 0; i < PARTICLE_COUNT; i += 1) {
    const angle = (Math.PI * 2 * i) / PARTICLE_COUNT;
    const radius = 150 + Math.random() * 250;
    particles.push({
      angle: angle,
      radius: radius,
      speed: 0.0003 + Math.random() * 0.0005,
      size: Math.random() * 2 + 1,
      opacity: Math.random() * 0.4 + 0.1,
      color: Math.random() > 0.5 ? 'cyan' : 'gold',
    });
  }
}

// Create nebula clouds
function createNebulaClouds() {
  nebulaClouds.length = 0;
  for (let i = 0; i < NEBULA_COUNT; i += 1) {
    nebulaClouds.push({
      x: Math.random() * nebulaCanvas.width,
      y: Math.random() * nebulaCanvas.height,
      radius: Math.random() * 300 + 200,
      drift: (Math.random() - 0.5) * 0.15,
      driftY: (Math.random() - 0.5) * 0.1,
      opacity: Math.random() * 0.15 + 0.05,
      hue: Math.random() > 0.5 ? 45 : 190, // Gold or cyan
    });
  }
}

// Spawn shooting star
function spawnShootingStar() {
  shooting.push({
    x: Math.random() * starCanvas.width * 0.7 + starCanvas.width * 0.15,
    y: Math.random() * starCanvas.height * 0.3,
    vx: -(Math.random() * 10 + 10),
    vy: Math.random() * 3 + 2,
    life: 1,
    tailLength: Math.random() * 30 + 40,
  });
}

// Draw nebula layer
function drawNebula() {
  nebulaCtx.clearRect(0, 0, nebulaCanvas.width, nebulaCanvas.height);

  for (const cloud of nebulaClouds) {
    cloud.x += cloud.drift;
    cloud.y += cloud.driftY;

    // Wrap around
    if (cloud.x > nebulaCanvas.width + cloud.radius) cloud.x = -cloud.radius;
    if (cloud.x < -cloud.radius) cloud.x = nebulaCanvas.width + cloud.radius;
    if (cloud.y > nebulaCanvas.height + cloud.radius) cloud.y = -cloud.radius;
    if (cloud.y < -cloud.radius) cloud.y = nebulaCanvas.height + cloud.radius;

    const gradient = nebulaCtx.createRadialGradient(
      cloud.x, cloud.y, 0,
      cloud.x, cloud.y, cloud.radius
    );
    gradient.addColorStop(0, `hsla(${cloud.hue}, 70%, 60%, ${cloud.opacity})`);
    gradient.addColorStop(0.5, `hsla(${cloud.hue}, 60%, 50%, ${cloud.opacity * 0.5})`);
    gradient.addColorStop(1, 'transparent');

    nebulaCtx.fillStyle = gradient;
    nebulaCtx.fillRect(0, 0, nebulaCanvas.width, nebulaCanvas.height);
  }
}

// Main star animation
function drawStars() {
  starCtx.clearRect(0, 0, starCanvas.width, starCanvas.height);

  // Parallax offset from mouse
  const parallaxX = (mouseX - starCanvas.width / 2) * 0.02;
  const parallaxY = (mouseY - starCanvas.height / 2) * 0.02;

  // Draw stars with parallax and twinkling
  for (const s of stars) {
    s.y += s.drift;
    s.twinkle += s.twinkleSpeed;

    if (s.y > starCanvas.height + 2) {
      s.y = -2;
      s.x = Math.random() * starCanvas.width;
    }

    const px = s.x + parallaxX * s.layer;
    const py = s.y + parallaxY * s.layer - scrollY * s.layer * 0.5;
    const twinkleAlpha = s.a * (0.7 + Math.sin(s.twinkle) * 0.3);

    starCtx.beginPath();
    starCtx.fillStyle = `rgba(190,220,255,${twinkleAlpha})`;
    starCtx.arc(px, py, s.r * (1 + s.layer * 0.3), 0, Math.PI * 2);
    starCtx.fill();

    // Add glow to brighter stars
    if (s.a > 0.7 && s.r > 1.2) {
      starCtx.beginPath();
      const gradient = starCtx.createRadialGradient(px, py, 0, px, py, s.r * 4);
      gradient.addColorStop(0, `rgba(190,220,255,${twinkleAlpha * 0.3})`);
      gradient.addColorStop(1, 'transparent');
      starCtx.fillStyle = gradient;
      starCtx.arc(px, py, s.r * 4, 0, Math.PI * 2);
      starCtx.fill();
    }
  }

  // Draw orbital particles (Venus ring)
  const centerX = starCanvas.width / 2 + parallaxX * 0.5;
  const centerY = starCanvas.height / 2 + parallaxY * 0.5 - scrollY * 0.3;

  for (const p of particles) {
    p.angle += p.speed;
    const x = centerX + Math.cos(p.angle) * p.radius;
    const y = centerY + Math.sin(p.angle) * p.radius * 0.6; // Ellipse

    const gradient = starCtx.createRadialGradient(x, y, 0, x, y, p.size * 3);
    if (p.color === 'gold') {
      gradient.addColorStop(0, `rgba(251, 191, 36, ${p.opacity})`);
      gradient.addColorStop(1, 'transparent');
    } else {
      gradient.addColorStop(0, `rgba(34, 211, 238, ${p.opacity})`);
      gradient.addColorStop(1, 'transparent');
    }

    starCtx.beginPath();
    starCtx.fillStyle = gradient;
    starCtx.arc(x, y, p.size * 3, 0, Math.PI * 2);
    starCtx.fill();

    starCtx.beginPath();
    starCtx.fillStyle = p.color === 'gold' ? '#fbbf24' : '#22d3ee';
    starCtx.arc(x, y, p.size, 0, Math.PI * 2);
    starCtx.fill();
  }

  // Draw shooting stars
  for (let i = shooting.length - 1; i >= 0; i -= 1) {
    const sh = shooting[i];
    sh.x += sh.vx;
    sh.y += sh.vy;
    sh.life -= 0.01;

    const gradient = starCtx.createLinearGradient(
      sh.x, sh.y,
      sh.x - sh.vx * 3, sh.y - sh.vy * 3
    );
    gradient.addColorStop(0, `rgba(255,245,220,${Math.max(0, sh.life)})`);
    gradient.addColorStop(0.5, `rgba(251,191,36,${Math.max(0, sh.life * 0.6)})`);
    gradient.addColorStop(1, 'transparent');

    starCtx.beginPath();
    starCtx.strokeStyle = gradient;
    starCtx.lineWidth = 2;
    starCtx.lineCap = 'round';
    starCtx.moveTo(sh.x, sh.y);
    starCtx.lineTo(sh.x - sh.vx * 3.5, sh.y - sh.vy * 3.5);
    starCtx.stroke();

    if (sh.life <= 0) shooting.splice(i, 1);
  }

  requestAnimationFrame(drawStars);
}

// Cursor glow effect
const cursorGlow = document.getElementById('cursor-glow');

// Mouse tracking with smoothing
let targetMouseX = window.innerWidth / 2;
let targetMouseY = window.innerHeight / 2;

function smoothMouseMove() {
  mouseX += (targetMouseX - mouseX) * 0.05;
  mouseY += (targetMouseY - mouseY) * 0.05;

  // Update cursor glow position
  if (cursorGlow) {
    cursorGlow.style.left = mouseX + 'px';
    cursorGlow.style.top = mouseY + 'px';
  }

  requestAnimationFrame(smoothMouseMove);
}

// Event listeners
window.addEventListener("resize", () => {
  resize();
  createStars();
  createParticles();
  createNebulaClouds();
});

window.addEventListener("mousemove", (e) => {
  targetMouseX = e.clientX;
  targetMouseY = e.clientY;

  // Show cursor glow
  if (cursorGlow) {
    cursorGlow.style.opacity = '1';
  }
});

window.addEventListener("mouseleave", () => {
  if (cursorGlow) {
    cursorGlow.style.opacity = '0';
  }
});

window.addEventListener("scroll", () => {
  scrollY = window.scrollY;
});

// Shooting star spawner
setInterval(() => {
  if (Math.random() < 0.5) spawnShootingStar();
}, 2200);

// Nebula animation loop
function animateNebula() {
  drawNebula();
  requestAnimationFrame(animateNebula);
}

// Smooth scroll for anchor links
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
  anchor.addEventListener('click', function (e) {
    e.preventDefault();
    const target = document.querySelector(this.getAttribute('href'));
    if (target) {
      target.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });
    }
  });
});

// Intersection Observer for scroll animations
const observerOptions = {
  threshold: 0.1,
  rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.style.opacity = '1';
      entry.target.style.transform = 'translateY(0)';
    }
  });
}, observerOptions);

// Observe sections for fade-in
document.querySelectorAll('section').forEach(section => {
  section.style.opacity = '0';
  section.style.transform = 'translateY(30px)';
  section.style.transition = 'opacity 0.8s ease-out, transform 0.8s ease-out';
  observer.observe(section);
});

// Initialize
resize();
createStars();
createParticles();
createNebulaClouds();
drawStars();
animateNebula();
smoothMouseMove();
