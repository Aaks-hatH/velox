/*
  The small amount of JavaScript the pages use. Everything works without it;
  this only adds motion and the chat.

  0. Background       - flowing red light that reacts to scrolling
  1. Heart rhythm     - a simulated heartbeat at your resting rate (drives the sun's beat)
  1b. Solar system    - the sun and orbiting measurement planets on Today
  2. Chart hover      - shows the value of the day under your finger or mouse
  3. Onboarding steps - shows one step at a time
  4. Ask page         - sends questions to the server and shows the answers
*/

document.documentElement.classList.add("js");
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/* ---------- 0. Flowing red light (the page background) ---------- */

/*
  Hundreds of hair-thin red fibres run down the middle of the screen, then fan out near
  the bottom: the outer fibres sweep sideways to the edges, the inner ones spread downwards.
  Most are faint, a few glow hot, and two are bright neon lines. Everything is drawn at full
  screen resolution with only a tight bloom, so it looks like real fibre optics, not haze.

  Light flows along every fibre:
    - not scrolling: it drifts downwards, gently
    - scrolling down: it turns round and rushes upwards
    - scrolling up: it rushes downwards
  The speed eases smoothly between these, so the change of direction feels fluid.
*/

const FLOW = {
  strands: 280,
  idleSpeed: 0.10,      // share of a fibre travelled per second when not scrolling (downwards)
  scrollSpeed: 0.55,    // speed while scrolling at a normal pace
  maxSpeed: 1.2,
  easing: 4,            // how quickly the speed catches up with the target (per second)
  pulsesPerStrand: 2,
};

function startFlowBackground(canvas) {
  const ctx = canvas.getContext("2d");
  let width = 0, height = 0, ratio = 1;
  let strands = [];
  let base = null;             // the still fibres, drawn once per size and reused
  let halo = null;             // half-size layer for the faint glow around moving light
  let phase = 0;               // how far the light has travelled
  let speed = FLOW.idleSpeed;  // current speed (positive = flowing down)
  let lastScrollY = window.scrollY;
  let lastScrollAt = 0;
  let scrollTarget = 0;
  let lastFrame = null;

  // Same fibres every time.
  let seed = 11;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  // Roughly bell-shaped random number in -1..1: packs more fibres into the middle.
  const bell = () => (random() + random() + random()) / 1.5 - 1;

  function makeStrands() {
    seed = 11;
    const list = [];
    const cx = width / 2;
    const column = Math.min(width * 0.08, 52);       // half-width of the fibre column
    for (let i = 0; i < FLOW.strands; i++) {
      const o = bell();                               // -1 (left) .. 1 (right)
      const side = Math.sign(o) || 1, reach = Math.min(1, Math.abs(o) * 1.15 + random() * 0.15);
      const x = cx + o * column;
      const kneeY = height * (0.62 + random() * 0.12);
      // Outer fibres sweep out to the sides; inner ones run on down to the bottom.
      const endY = height * (1.06 - 0.32 * reach ** 1.3) + (random() - 0.5) * height * 0.05;
      const endX = cx + side * (reach ** 0.85) * width * (0.55 + random() * 0.4);
      const glow = random() ** 3;                     // most fibres dim, a few hot
      list.push(strand(x, kneeY, endX, endY, 0.25 + random() * 0.6 + glow * 0.5, glow, 346 + random() * 18, false));
    }
    // The two neon lines in the column.
    for (const o of [-0.34, 0.34]) {
      const side = Math.sign(o);
      list.push(strand(cx + o * column, height * 0.7, cx + side * width * 0.5, height * 1.08, 1.1, 1, 350, true));
    }
    return list;
  }

  function strand(x, kneeY, endX, endY, lineWidth, glow, hue, neon) {
    return {
      top: { x, y: -20 },
      knee: { x, y: kneeY },
      c1: { x, y: kneeY + (endY - kneeY) * 0.55 },
      c2: { x: x + (endX - x) * 0.12, y: endY },
      end: { x: endX, y: endY },
      straight: 0.55,              // share of the fibre that is the straight part
      width: lineWidth, glow, hue, neon, offset: random(), pace: 0.85 + random() * 0.3,
    };
  }

  // A point on a fibre, u from 0 at the top to 1 at its end.
  function pointOn(s, u) {
    if (u <= s.straight) {
      const t = u / s.straight;
      return { x: s.top.x, y: s.top.y + (s.knee.y - s.top.y) * t };
    }
    const t = (u - s.straight) / (1 - s.straight), v = 1 - t;
    return {
      x: v * v * v * s.knee.x + 3 * v * v * t * s.c1.x + 3 * v * t * t * s.c2.x + t * t * t * s.end.x,
      y: v * v * v * s.knee.y + 3 * v * v * t * s.c1.y + 3 * v * t * t * s.c2.y + t * t * t * s.end.y,
    };
  }

  function strandPath(g, s) {
    g.beginPath();
    g.moveTo(s.top.x, s.top.y);
    g.lineTo(s.knee.x, s.knee.y);
    g.bezierCurveTo(s.c1.x, s.c1.y, s.c2.x, s.c2.y, s.end.x, s.end.y);
  }

  function layer(scale) {
    const c = document.createElement("canvas");
    c.width = Math.max(1, Math.round(width * scale));
    c.height = Math.max(1, Math.round(height * scale));
    const g = c.getContext("2d");
    g.setTransform(scale, 0, 0, scale, 0, 0);    // draw using normal page coordinates
    g.lineCap = "round";
    return { canvas: c, g };
  }

  // The still part: black page, a faint warm depth where the fan opens, then the fibres:
  // crisp hairlines with a tight bloom hugging them.
  function buildBase() {
    const out = layer(ratio);
    const g = out.g;
    g.fillStyle = "#000";
    g.fillRect(0, 0, width, height);

    // Faint warmth behind the fan, kept low so it reads as depth rather than smoke.
    g.save();
    g.translate(width / 2, height * 0.74);
    g.scale(1, 0.3);
    const fan = g.createRadialGradient(0, 0, 0, 0, 0, width * 0.8);
    fan.addColorStop(0, "rgba(200, 30, 30, 0.22)");
    fan.addColorStop(1, "rgba(80, 0, 8, 0)");
    g.fillStyle = fan;
    g.fillRect(-width, -height * 3, width * 2, height * 6);
    g.restore();

    // The fibres on their own sharp layer.
    const lines = layer(ratio);
    const l = lines.g;
    l.globalCompositeOperation = "lighter";
    for (const st of strands) {
      l.strokeStyle = st.neon
        ? "rgba(255, 150, 175, 0.9)"
        : `hsla(${st.hue}, 95%, ${40 + st.glow * 25}%, ${0.16 + st.glow * 0.55})`;
      l.lineWidth = st.width;
      strandPath(l, st);
      l.stroke();
      // Hot fibres and the neon lines get a pale core, like light inside glass.
      if (st.neon || st.glow > 0.55) {
        l.strokeStyle = st.neon ? "rgba(255, 228, 234, 0.95)" : `hsla(${st.hue + 8}, 100%, 82%, ${st.glow * 0.45})`;
        l.lineWidth = Math.max(0.3, st.width * 0.4);
        strandPath(l, st);
        l.stroke();
      }
    }

    // Bloom: two tight blurs of the fibres under the sharp copy.
    g.globalCompositeOperation = "lighter";
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.filter = `blur(${(6 * ratio).toFixed(1)}px)`;
    g.globalAlpha = 0.55;
    g.drawImage(lines.canvas, 0, 0);
    g.filter = `blur(${(1.6 * ratio).toFixed(1)}px)`;
    g.globalAlpha = 0.8;
    g.drawImage(lines.canvas, 0, 0);
    g.filter = "none";
    g.globalAlpha = 1;
    g.drawImage(lines.canvas, 0, 0);

    // Fade the top to black so the column seems to come from far away.
    g.setTransform(ratio, 0, 0, ratio, 0, 0);
    g.globalCompositeOperation = "source-over";
    const top = g.createLinearGradient(0, 0, 0, height * 0.4);
    top.addColorStop(0, "rgba(0, 0, 0, 0.85)");
    top.addColorStop(1, "rgba(0, 0, 0, 0)");
    g.fillStyle = top;
    g.fillRect(0, 0, width, height * 0.4);
    return out.canvas;
  }

  function resize() {
    ratio = Math.min(window.devicePixelRatio || 1, 2);   // full sharpness on retina screens
    width = canvas.clientWidth || window.innerWidth;   // the phone-wide column, not the whole window
    height = window.innerHeight;
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    strands = makeStrands();
    base = buildBase();
    halo = layer(0.5);
    if (reduceMotion) draw();
  }

  // One pulse of light running along a fibre: bright at its head, fading back along its tail.
  function streak(g, st, head, length, widthPx, color) {
    const tail = speed >= 0 ? head - length : head + length;   // the tail trails behind
    const a = pointOn(st, Math.min(1, Math.max(0, tail)));
    const b = pointOn(st, head);
    const gradient = g.createLinearGradient(a.x, a.y, b.x, b.y);
    gradient.addColorStop(0, "rgba(255, 40, 60, 0)");
    gradient.addColorStop(1, color);
    g.strokeStyle = gradient;
    g.lineWidth = widthPx;
    g.beginPath();
    for (let k = 0; k <= 8; k++) {
      const q = pointOn(st, Math.min(1, Math.max(0, tail + ((head - tail) * k) / 8)));
      k === 0 ? g.moveTo(q.x, q.y) : g.lineTo(q.x, q.y);
    }
    g.stroke();
  }

  function draw() {
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalCompositeOperation = "source-over";
    ctx.drawImage(base, 0, 0);
    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";

    // The faint glow around the brighter pulses goes on a half-size layer.
    const h = halo.g;
    h.setTransform(1, 0, 0, 1, 0, 0);
    h.clearRect(0, 0, halo.canvas.width, halo.canvas.height);
    h.setTransform(0.5, 0, 0, 0.5, 0, 0);
    h.globalCompositeOperation = "lighter";

    for (const st of strands) {
      for (let p = 0; p < FLOW.pulsesPerStrand; p++) {
        const head = (((phase * st.pace + st.offset + p / FLOW.pulsesPerStrand) % 1) + 1) % 1;
        if (st.neon) {
          streak(h, st, head, 0.16, 7, "rgba(255, 80, 115, 0.5)");
          streak(ctx, st, head, 0.12, 1.4, "rgba(255, 236, 240, 1)");
        } else {
          const light = 0.25 + st.glow * 0.7;
          if (st.glow > 0.3) streak(h, st, head, 0.12, 4, `hsla(${st.hue}, 100%, 55%, ${0.18 * light})`);
          streak(ctx, st, head, 0.1, st.width + 0.15, `hsla(${st.hue + 6}, 100%, ${62 + st.glow * 20}%, ${light})`);
        }
      }
    }
    ctx.imageSmoothingQuality = "high";
    ctx.drawImage(halo.canvas, 0, 0, width, height);
    ctx.globalCompositeOperation = "source-over";
  }

  // Scrolling sets which way, and how fast, the light should flow.
  window.addEventListener("scroll", () => {
    const y = window.scrollY;
    const delta = y - lastScrollY;
    lastScrollY = y;
    if (delta === 0) return;
    lastScrollAt = performance.now();
    const pace = Math.min(FLOW.maxSpeed, FLOW.scrollSpeed + Math.abs(delta) * 0.012);
    scrollTarget = delta > 0 ? -pace : pace;   // down the page = light flows up, and the reverse
  }, { passive: true });

  function frame(timeMs) {
    requestAnimationFrame(frame);
    const dt = lastFrame === null ? 0 : Math.min(0.05, (timeMs - lastFrame) / 1000);
    lastFrame = timeMs;
    // Shortly after scrolling stops, go back to the slow downward drift.
    const scrolling = performance.now() - lastScrollAt < 140;
    const target = scrolling ? scrollTarget : FLOW.idleSpeed;
    speed += (target - speed) * Math.min(1, dt * FLOW.easing);
    phase += speed * dt;
    draw();
  }

  window.addEventListener("resize", resize);
  resize();
  if (!reduceMotion) requestAnimationFrame(frame);
}

const flowCanvas = document.getElementById("flow-bg");
if (flowCanvas) startFlowBackground(flowCanvas);

/* ---------- 1. Heart rhythm ---------- */

/*
  Velox Health doesn't read your heart live; this is a gentle, realistic rhythm at your resting
  heart rate, used to make the sun on Today beat. It behaves like a real heart:
    - Each beat has the textbook shape: small P wave, sharp Q-R-S spike, rounded T wave.
    - The spike always takes ~0.1 s, whatever the heart rate (only the pause between beats changes).
    - The time between beats speeds up when breathing in and slows when breathing out
      ("respiratory sinus arrhythmia"), plus a little randomness, like a real pulse.
    - The baseline drifts gently with breathing, and each beat's height varies slightly.
*/

const BREATH_SECONDS = 4.2;   // one breath in and out

// The shape of one beat around its R peak (time 0, in seconds). Each part is a bell curve.
function beatShape(t) {
  const bell = (center, width, height) => height * Math.exp(-(((t - center) / width) ** 2));
  const tWaveWidth = t < 0.26 ? 0.065 : 0.045;          // the T wave rises slowly and falls faster
  return bell(-0.17, 0.028, 0.11)    // P wave: the upper chambers contract
       + bell(-0.028, 0.009, -0.11)  // Q dip
       + bell(0, 0.0115, 1.0)        // R spike: the main chambers contract
       + bell(0.03, 0.011, -0.27)    // S dip
       + bell(0.26, tWaveWidth, 0.27); // T wave: the heart muscle resets
}

// Creates a heart that beats at about `bpm` and can report its signal at any moment.
function createHeart(bpm) {
  const beats = [];   // [{ time, size }], times of the R peaks in seconds
  let next = 0;

  function addBeatsUntil(time) {
    while (next < time + 2) {
      const breathing = Math.sin((2 * Math.PI * next) / BREATH_SECONDS);
      const interval = (60 / bpm) * (1 - 0.05 * breathing + (Math.random() - 0.5) * 0.04);
      beats.push({ time: next, size: 0.93 + Math.random() * 0.1 });
      next += interval;
    }
    while (beats.length > 12) beats.shift();   // forget beats that are long gone
  }

  return {
    // The signal (about -0.3 to 1) at `time` seconds.
    signalAt(time) {
      addBeatsUntil(time);
      let value = 0.035 * Math.sin((2 * Math.PI * time) / BREATH_SECONDS);   // breathing drift
      for (const beat of beats) {
        const t = time - beat.time;
        if (t > -0.4 && t < 0.6) value += beatShape(t) * beat.size;
      }
      return value;
    },
    // Has an R peak happened between two moments? (used to pulse the bpm number)
    beatBetween(from, to) {
      return beats.some((beat) => beat.time > from && beat.time <= to);
    },
    // Seconds since the most recent beat (used to make the sun's strands throb).
    sinceBeat(time) {
      addBeatsUntil(time);
      let last = -Infinity;
      for (const beat of beats) if (beat.time <= time && beat.time > last) last = beat.time;
      return time - last;
    },
  };
}

// One heart per page, shared by everything that beats.
const hearts = new Map();
function heartFor(bpm) {
  if (!hearts.has(bpm)) hearts.set(bpm, createHeart(bpm));
  return hearts.get(bpm);
}

// Makes every [data-pulse] element "thump" once. Several animations may ask on the same beat,
// so it ignores repeat calls within 0.2 s.
let lastPulse = 0;
function pulseBeat() {
  const now = performance.now();
  if (now - lastPulse < 200) return;
  lastPulse = now;
  document.querySelectorAll("[data-pulse]").forEach((el) => {
    el.classList.remove("beat"); void el.offsetWidth; el.classList.add("beat");
  });
}


/* ---------- 1b. Solar system (Today) ---------- */

/*
  The sun is a ring of glowing strands, like fibre-optic threads seen end-on. On the first
  visit the strands start scattered and gather into the ring. It turns slowly and swells a
  little on every heartbeat.

  Each measurement is a planet on an oval orbit. The planets are held in a web of threads:
    - a small bundle of threads from each planet to the sun,
    - a thread to each neighbour on the orbit,
    - and a longer thread to the planet two along.

  Tapping a planet sends energy through EVERY thread towards it. It starts at the planets
  furthest away (counted in threads), flows through the sun and the nearer planets, and pours
  into the tapped one. The planet charges up, bursts, and its colour floods the screen as
  its page opens.
*/

const SUN = {
  strands: 230,
  hole: 0.075,         // radius of the empty middle, as a share of the box width
  minLength: 0.045,    // strand lengths, as a share of the box width
  maxLength: 0.10,
  spin: 0.05,          // radians per second
  orbitSeconds: 160,   // one full trip round the orbit
  bundle: 3,           // threads between each planet and the sun
  hop: 0.42,           // seconds for energy to cross one thread
  packets: 4,          // bursts of energy sent along each thread
  packetGap: 0.08,     // seconds between those bursts
};
const SUN_COLOR = "#E8822A";

function makeStrands(random) {
  const strands = [];
  for (let i = 0; i < SUN.strands; i++) {
    strands.push({
      angle: (i / SUN.strands) * Math.PI * 2 + (random() - 0.5) * 0.03,
      length: SUN.minLength + (SUN.maxLength - SUN.minLength) * random() ** 0.7,
      width: 0.8 + random() * 1.5,
      baseHue: 4 + random() * 16,     // deep red-orange where the strand starts
      tipHue: 30 + random() * 16,     // warm amber at the tip
      // Where it floats before the intro gathers it into the ring:
      scatterX: (random() - 0.5) * 0.9,
      scatterY: (random() - 0.5) * 0.7,
      scatterAngle: random() * Math.PI * 2,
      delay: random() * 0.55,
    });
  }
  return strands;
}

// Draws one strand from (x1, y1) at its root to (x2, y2) at its tip.
// Tuned for a light page: rich, slightly deep colours rather than pale glow.
function drawStrand(ctx, x1, y1, x2, y2, strand, alpha = 1) {
  const gradient = ctx.createLinearGradient(x1, y1, x2, y2);
  gradient.addColorStop(0, `hsla(${strand.baseHue}, 80%, 34%, ${0.10 * alpha})`);
  gradient.addColorStop(0.5, `hsla(${(strand.baseHue + strand.tipHue) / 2}, 90%, 46%, ${0.75 * alpha})`);
  gradient.addColorStop(1, `hsla(${strand.tipHue}, 100%, 55%, ${alpha})`);
  ctx.strokeStyle = gradient;
  ctx.lineWidth = strand.width;
  ctx.beginPath();
  ctx.moveTo(x1, y1);
  ctx.lineTo(x2, y2);
  ctx.stroke();
  ctx.fillStyle = `hsla(${strand.tipHue + 6}, 100%, 62%, ${0.85 * alpha})`;
  ctx.beginPath();
  ctx.arc(x2, y2, strand.width * 0.75, 0, Math.PI * 2);
  ctx.fill();
}

// A point on a curved thread (a quadratic curve from a, bent towards c, ending at b); u from 0 to 1.
function curvePoint(a, c, b, u) {
  const v = 1 - u;
  return { x: v * v * a.x + 2 * v * u * c.x + u * u * b.x, y: v * v * a.y + 2 * v * u * c.y + u * u * b.y };
}

// The web: which nodes are joined. Planets are 0..n-1 and the sun is "sun".
function buildWeb(count) {
  const links = [];
  for (let i = 0; i < count; i++) {
    links.push({ from: "sun", to: i, threads: SUN.bundle, kind: "sun" });
    links.push({ from: i, to: (i + 1) % count, threads: 1, kind: "ring" });
    if (count > 4) links.push({ from: i, to: (i + 2) % count, threads: 1, kind: "skip" });
  }
  return links;
}

// How many threads each node is from the target (a breadth-first search).
function threadDistances(links, count, target) {
  const nodes = ["sun", ...Array.from({ length: count }, (_, i) => i)];
  const distance = new Map(nodes.map((n) => [n, Infinity]));
  distance.set(target, 0);
  const queue = [target];
  while (queue.length) {
    const node = queue.shift();
    for (const link of links) {
      const other = link.from === node ? link.to : link.to === node ? link.from : null;
      if (other !== null && distance.get(other) === Infinity) {
        distance.set(other, distance.get(node) + 1);
        queue.push(other);
      }
    }
  }
  return distance;
}

function startSystem(system) {
  const canvas = system.querySelector(".system-canvas");
  const ctx = canvas.getContext("2d");
  const planets = [...system.querySelectorAll("[data-planet]")];
  const heart = heartFor(Number(system.dataset.bpm) || 60);
  const flagColor = getComputedStyle(document.documentElement).getPropertyValue("--flag").trim();
  const threadColor = getComputedStyle(document.documentElement).getPropertyValue("--thread").trim() || "#fff";
  const links = buildWeb(planets.length);
  const colorOf = (node) => (node === "sun" ? SUN_COLOR : planets[node].dataset.color);

  // Same strands every time (a fixed seed), so the sun always looks the same.
  let seed = 7;
  const random = () => ((seed = (seed * 16807) % 2147483647) - 1) / 2147483646;
  const strands = makeStrands(random);

  let width = 0, height = 0, ratio = 1;
  let sprite = null;          // the faint rays, drawn once and reused every frame
  let surge = null;           // the energy rush while a tapped planet charges up
  let lastTime = null;

  // The full gathering intro plays once per visit; afterwards the sun just blooms open.
  let introLength = 0.55;
  try {
    if (!sessionStorage.getItem("sunSeen")) introLength = 1.5;
    sessionStorage.setItem("sunSeen", "yes");
  } catch (e) {}
  let introStart = null;

  function resize() {
    ratio = window.devicePixelRatio || 1;
    width = canvas.clientWidth;
    height = canvas.clientHeight;
    canvas.width = width * ratio;
    canvas.height = height * ratio;
    sprite = width > 0 ? buildSprite() : null;
    if (reduceMotion) frame(0);
  }

  // Pre-draw the faint rays around the ring onto a small hidden canvas.
  function buildSprite() {
    const size = Math.ceil(width * (SUN.hole + SUN.maxLength + 0.08) * 2);
    const off = document.createElement("canvas");
    off.width = off.height = size * ratio;
    const g = off.getContext("2d");
    g.scale(ratio, ratio);
    g.translate(size / 2, size / 2);
    g.globalCompositeOperation = "lighter";   // overlapping strands add up into a glow
    g.lineCap = "round";
    // Thin rays reaching beyond the ring. (The strands themselves are drawn live, so they can beat.)
    for (let i = 0; i < 48; i++) {
      const a = (i / 48) * Math.PI * 2 + random() * 0.05;
      const r1 = width * (SUN.hole + SUN.maxLength * 0.9), r2 = r1 + width * (0.02 + random() * 0.05);
      g.strokeStyle = `rgba(255, 215, 170, ${0.06 + random() * 0.12})`;
      g.lineWidth = 0.8;
      g.beginPath();
      g.moveTo(Math.cos(a) * r1, Math.sin(a) * r1);
      g.lineTo(Math.cos(a) * r2, Math.sin(a) * r2);
      g.stroke();
    }
    return { canvas: off, size };
  }

  // Where each planet sits right now on its oval orbit.
  function planetPositions(time) {
    const cx = width / 2, cy = height / 2;
    const rx = width / 2 - 44, ry = height / 2 - 58;
    const turn = reduceMotion ? 0 : (time / SUN.orbitSeconds) * Math.PI * 2;
    return planets.map((_, i) => {
      const a = -Math.PI / 2 + (i / planets.length) * Math.PI * 2 + turn;
      return { x: cx + Math.cos(a) * rx, y: cy + Math.sin(a) * ry };
    });
  }

  // The shape of every thread this frame: start a, bend c, end b, for each link and each thread in it.
  function threadShapes(time, positions, sunScale) {
    const cx = width / 2, cy = height / 2;
    const sunEdge = width * (SUN.hole + SUN.maxLength * 0.75) * sunScale;
    const shapes = [];
    links.forEach((link, l) => {
      for (let k = 0; k < link.threads; k++) {
        let a, b, c;
        const sway = Math.sin(time * 0.8 + l * 1.7 + k * 2.1) * 6;
        if (link.kind === "sun") {
          // A fan of threads: they leave the sun a little apart and meet at the planet.
          const p = positions[link.to];
          const base = Math.atan2(p.y - cy, p.x - cx);
          const spread = (k - (link.threads - 1) / 2) * 0.16;
          a = { x: cx + Math.cos(base + spread) * sunEdge, y: cy + Math.sin(base + spread) * sunEdge };
          const length = Math.hypot(p.x - a.x, p.y - a.y);
          b = { x: p.x - ((p.x - a.x) / length) * 24, y: p.y - ((p.y - a.y) / length) * 24 };
          const nx = -(b.y - a.y) / length, ny = (b.x - a.x) / length;
          c = { x: (a.x + b.x) / 2 + nx * (spread * 40 + sway), y: (a.y + b.y) / 2 + ny * (spread * 40 + sway) };
        } else {
          // Between planets: the thread bows outwards, away from the sun.
          const p = positions[link.from], q = positions[link.to];
          const length = Math.hypot(q.x - p.x, q.y - p.y);
          const ux = (q.x - p.x) / length, uy = (q.y - p.y) / length;
          a = { x: p.x + ux * 24, y: p.y + uy * 24 };
          b = { x: q.x - ux * 24, y: q.y - uy * 24 };
          const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
          const away = Math.hypot(mx - cx, my - cy) || 1;
          const bow = (link.kind === "skip" ? 26 : 12) + sway;
          c = { x: mx + ((mx - cx) / away) * bow, y: my + ((my - cy) / away) * bow };
        }
        shapes.push({ link, a, b, c, k });
      }
    });
    return shapes;
  }

  function drawWeb(shapes, time) {
    const charging = surge ? Math.min(1, (performance.now() - surge.start) / 400) : 0;
    for (const s of shapes) {
      const flagged = s.link.kind === "sun" && planets[s.link.to].classList.contains("flagged");
      ctx.strokeStyle = flagged ? flagColor : threadColor;
      ctx.globalAlpha = (flagged ? 0.45 : s.link.kind === "sun" ? 0.16 : 0.10) + charging * 0.18;
      ctx.lineWidth = s.link.kind === "sun" ? 0.8 : 0.7;
      ctx.beginPath();
      ctx.moveTo(s.a.x, s.a.y);
      ctx.quadraticCurveTo(s.c.x, s.c.y, s.b.x, s.b.y);
      ctx.stroke();

      // At rest, specks of light drift outwards from the sun along the first thread of each bundle.
      if (!surge && !reduceMotion && s.link.kind === "sun" && s.k === 1) {
        const u = (time * 0.3 + s.link.to * 0.13) % 1;
        const q = curvePoint(s.a, s.c, s.b, u);
        ctx.globalAlpha = Math.sin(Math.PI * u) * 0.85;
        ctx.fillStyle = colorOf(s.link.to);
        ctx.beginPath();
        ctx.arc(q.x, q.y, 1.7, 0, Math.PI * 2);
        ctx.fill();
      }
    }
    ctx.globalAlpha = 1;
  }

  // The energy rush: packets of light travel along every thread towards the tapped planet.
  function drawSurge(shapes) {
    const elapsed = (performance.now() - surge.start) / 1000;
    for (const s of shapes) {
      const dFrom = surge.distance.get(s.link.from), dTo = surge.distance.get(s.link.to);
      if (dFrom === dTo) continue;                         // runs sideways: nothing to carry
      const forward = dFrom > dTo;                         // which way is "towards the target"
      const source = forward ? s.link.from : s.link.to;
      const start = (surge.furthest - Math.max(dFrom, dTo)) * SUN.hop;
      const color = colorOf(source);
      for (let p = 0; p < SUN.packets; p++) {
        const t = (elapsed - start - p * SUN.packetGap - s.k * 0.03) / SUN.hop;
        if (t < 0 || t > 1) continue;
        const u = forward ? t : 1 - t;
        // A bright head with a short fading tail behind it.
        for (let tail = 0; tail < 4; tail++) {
          const back = (forward ? -1 : 1) * tail * 0.035;
          const q = curvePoint(s.a, s.c, s.b, Math.min(1, Math.max(0, u + back)));
          ctx.globalAlpha = (1 - tail / 4) * 0.95;
          ctx.fillStyle = tail === 0 ? "#FFFFFF" : color;
          ctx.shadowColor = color;
          ctx.shadowBlur = tail === 0 ? 14 : 0;
          ctx.beginPath();
          ctx.arc(q.x, q.y, tail === 0 ? 3.2 : 2.6 - tail * 0.5, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    ctx.shadowBlur = 0;
    ctx.globalAlpha = 1;
  }

  function drawSun(time, scale, intro) {
    const cx = width / 2, cy = height / 2;
    const spin = reduceMotion ? 0 : time * SUN.spin;
    const outer = width * (SUN.hole + SUN.maxLength);

    // Warm haze behind the ring.
    const haze = ctx.createRadialGradient(cx, cy, width * SUN.hole * 0.5, cx, cy, outer * 1.9 * scale);
    haze.addColorStop(0, "rgba(255, 150, 70, 0.26)");
    haze.addColorStop(0.45, "rgba(255, 140, 60, 0.10)");
    haze.addColorStop(1, "rgba(255, 140, 60, 0)");
    ctx.fillStyle = haze;
    ctx.fillRect(0, 0, width, height);

    ctx.save();
    ctx.globalCompositeOperation = "lighter";
    ctx.lineCap = "round";
    if (intro >= 1 && sprite) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate(spin);
      ctx.scale(scale, scale);
      ctx.drawImage(sprite.canvas, -sprite.size / 2, -sprite.size / 2, sprite.size, sprite.size);
      ctx.restore();
    }
    for (const s of strands) {
      const a = s.angle + spin;
      const r1 = width * SUN.hole * scale;
      const r2 = r1 + width * s.length * scale;
      const ring = [cx + Math.cos(a) * r1, cy + Math.sin(a) * r1, cx + Math.cos(a) * r2, cy + Math.sin(a) * r2];
      if (intro < 1) {
        // Gathering: each strand flies from its scattered spot into the ring.
        const p = Math.min(1, Math.max(0, (intro * 1.45 - s.delay) / 0.9));
        const e = 1 - (1 - p) ** 3;
        const sx = cx + s.scatterX * width, sy = cy + s.scatterY * height;
        const sx2 = sx + Math.cos(s.scatterAngle) * width * s.length, sy2 = sy + Math.sin(s.scatterAngle) * width * s.length;
        const mix = (from, to) => from + (to - from) * e;
        drawStrand(ctx, mix(sx, ring[0]), mix(sy, ring[1]), mix(sx2, ring[2]), mix(sy2, ring[3]), s, 0.35 + 0.65 * e);
      } else {
        drawStrand(ctx, ring[0], ring[1], ring[2], ring[3], s, 0.9);
      }
    }
    ctx.restore();
  }


  function frame(timeMs) {
    if (!reduceMotion) requestAnimationFrame(frame);
    if (width === 0) return;
    const time = timeMs / 1000;
    if (introStart === null) introStart = time;
    const intro = reduceMotion ? 1 : Math.min(1, (time - introStart) / introLength);

    // The sun opens up during the intro and flares while energy passes through it.
    // Its strands stay steady; only the number in the middle keeps the heartbeat.
    const bloom = introLength < 1 ? 0.55 + 0.45 * (1 - (1 - intro) ** 3) : 1;
    let flare = 0;
    if (surge) {
      const t = (performance.now() - surge.start) / 1000 - (surge.furthest - 2) * SUN.hop;
      flare = Math.max(0, Math.sin(Math.min(1, Math.max(0, t / (SUN.hop * 2))) * Math.PI)) * 0.14;
    }
    const sunScale = bloom * (1 + flare);
    if (lastTime !== null && heart.beatBetween(lastTime - 0.03, time - 0.03)) pulseBeat();
    lastTime = time;

    const positions = planetPositions(time);
    planets.forEach((planet, i) => {
      const p = positions[i];
      // Planets drift into their places as the intro plays.
      const enter = Math.min(1, Math.max(0, intro * 1.6 - 0.35 - i * 0.05));
      const e = 1 - (1 - enter) ** 3;
      const x = (p.x - width / 2) * e, y = (p.y - height / 2) * e;
      planet.style.transform = `translate(${x}px, ${y}px) scale(${0.4 + 0.6 * e})`;
      planet.style.opacity = planet.classList.contains("faint") ? 0.55 * e : e;
    });

    // The tapped planet fills up with the energy arriving through its threads.
    if (surge) {
      const charge = Math.min(1, ((performance.now() - surge.start) / 1000) / surge.duration);
      planets[surge.target].style.setProperty("--charge", (charge ** 2).toFixed(3));
    }

    ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    ctx.clearRect(0, 0, width, height);
    const shapes = threadShapes(time, positions, sunScale);
    drawWeb(shapes, time);
    drawSun(time, sunScale, intro);
    if (surge) drawSurge(shapes);
  }

  // Tapping a planet: energy rushes to it through every thread, it bursts, its colour floods
  // the screen, then its page opens.
  planets.forEach((planet, index) => {
    planet.addEventListener("click", (event) => {
      if (reduceMotion || event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0 || surge) return;
      event.preventDefault();
      const distance = threadDistances(links, planets.length, index);
      const furthest = Math.max(...distance.values());
      const duration = furthest * SUN.hop + (SUN.packets - 1) * SUN.packetGap + 0.1;
      surge = { target: index, distance, furthest, duration, start: performance.now() };
      planet.classList.add("charging");

      const burstAt = duration * 1000;
      setTimeout(() => planet.classList.add("pinged"), burstAt - 120);
      setTimeout(() => {
        const box = planet.querySelector(".icon").getBoundingClientRect();
        const warp = document.getElementById("warp");
        warp.style.setProperty("--wx", `${box.left - warp.getBoundingClientRect().left + box.width / 2}px`);
        warp.style.setProperty("--wy", `${box.top + box.height / 2}px`);
        warp.style.setProperty("--warp-color", planet.dataset.color);
        void getComputedStyle(warp).clipPath;   // lock in the start point before growing from it
        warp.classList.add("go");
        try { sessionStorage.setItem("planetWarp", planet.dataset.color); } catch (e) {}
      }, burstAt + 200);
      setTimeout(() => { window.location.href = planet.href; }, burstAt + 780);
    });
  });

  // Coming back with the browser's Back button: clear the leftover colour and charge.
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    document.getElementById("warp")?.classList.remove("go");
    planets.forEach((planet) => {
      planet.classList.remove("pinged", "charging");
      planet.style.removeProperty("--charge");
    });
    surge = null;
  });

  new ResizeObserver(resize).observe(canvas);
  if (!reduceMotion) requestAnimationFrame(frame);
}

document.querySelectorAll("[data-system]").forEach(startSystem);

/* ---------- 2. Chart hover ---------- */

document.querySelectorAll(".chart-wrap").forEach((wrap) => {
  const points = JSON.parse(wrap.dataset.points || "[]");
  const svg = wrap.querySelector("svg");
  const cursor = svg.querySelector(".cursor");
  const label = document.querySelector("[data-caption-label]");
  const value = document.querySelector("[data-caption-value]");
  const original = [label.textContent, value.textContent];
  const width = svg.viewBox.baseVal.width;

  function show(event) {
    const box = svg.getBoundingClientRect();
    const position = (event.clientX - box.left) / box.width;          // 0 = left edge, 1 = right edge
    let nearest = points[0];
    for (const p of points) if (Math.abs(p.x - position) < Math.abs(nearest.x - position)) nearest = p;
    cursor.setAttribute("x1", nearest.x * width);
    cursor.setAttribute("x2", nearest.x * width);
    cursor.setAttribute("visibility", "visible");
    label.textContent = nearest.label;
    value.textContent = nearest.value;
  }

  function hide() {
    cursor.setAttribute("visibility", "hidden");
    [label.textContent, value.textContent] = original;
  }

  wrap.addEventListener("pointermove", show);
  wrap.addEventListener("pointerdown", show);
  wrap.addEventListener("pointerleave", hide);
});

/* ---------- 3. Onboarding steps ---------- */

const steps = document.querySelectorAll("#steps .step");
if (steps.length) {
  const dots = document.querySelectorAll("#steps .dots i");
  let current = 0;

  // Show one step. With `animate`, the old step slides away first, then the new one slides in.
  const showStep = (index, animate = false) => {
    const old = steps[current];
    const reveal = () => {
      steps.forEach((step, i) => {
        step.classList.remove("leaving", "entering");
        step.classList.toggle("current", i === index);
      });
      if (animate) steps[index].classList.add("entering");
      dots.forEach((dot, i) => dot.classList.toggle("on", i === index));
      window.scrollTo({ top: 0 });
      current = index;
    };
    if (animate && !reduceMotion && old !== steps[index]) {
      old.classList.add("leaving");
      setTimeout(reveal, 160);
    } else {
      reveal();
    }
  };
  document.querySelectorAll("#steps .next").forEach((button) =>
    button.addEventListener("click", () => {
      // "About you" checks its fields first and points at the first one that needs fixing.
      if (button.hasAttribute("data-validate")) {
        const fields = [...steps[current].querySelectorAll("input, select")];
        const bad = fields.find((field) => !field.checkValidity());
        if (bad) { bad.reportValidity(); bad.focus(); return; }
      }
      showStep(current + 1, true);
    }));

  // A button with data-requires="agree" stays locked until the checkbox with id "agree" is ticked.
  document.querySelectorAll("#steps [data-requires]").forEach((button) => {
    const box = document.getElementById(button.dataset.requires);
    const update = () => { button.disabled = !box.checked; };
    box.addEventListener("change", update);
    update();
  });

  // Leaving the introduction (finished or skipped) lets this tab into the app until the next refresh.
  document.getElementById("steps").addEventListener("submit", () => {
    try { sessionStorage.setItem("entered", "yes"); } catch (e) {}
  });

  // If the server sent us back (a missing detail, or "I agree" not ticked), open that step again.
  const errorStep = document.querySelector("#steps [data-error-step]")?.closest(".step");
  current = errorStep ? [...steps].indexOf(errorStep) : 0;
  showStep(current);
}

/* ---------- Numbers that count up ---------- */

// Elements like <b data-count="66" data-decimals="0">66</b> roll up from 0 to their value.
// Only the first time Today is opened in a visit, so coming back from a chart doesn't replay it.
const counters = document.querySelectorAll("[data-count]");
if (counters.length && !reduceMotion && !sessionStorage.getItem("counted")) {
  sessionStorage.setItem("counted", "yes");
  counters.forEach((el, index) => {
    const target = Number(el.dataset.count);
    const decimals = Number(el.dataset.decimals || 0);
    const format = (n) => n.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    const duration = 700, delay = 120 + index * 40;
    const startAt = performance.now() + delay;
    el.textContent = format(0);
    const tick = (now) => {
      const progress = Math.min(1, Math.max(0, (now - startAt) / duration));
      const eased = 1 - (1 - progress) ** 4;              // fast at first, gently settling
      el.textContent = format(target * eased);
      if (progress < 1) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
}

/* ---------- "Ask AI" bar ---------- */

// Sending the bar empty asks the page's suggested question instead.
document.querySelectorAll("[data-ask-dock]").forEach((dock) => {
  dock.addEventListener("submit", () => {
    const input = dock.querySelector("input");
    if (!input.value.trim()) input.value = input.dataset.default;
  });
});

/* ---------- 4. Ask page ---------- */

const form = document.getElementById("ask-form");
if (form) {
  const chat = document.getElementById("chat");
  const input = document.getElementById("question");
  const sendButton = form.querySelector("button");
  const suggestions = document.getElementById("suggestions");

  const updateButton = () => { sendButton.disabled = !input.value.trim(); };
  input.addEventListener("input", updateButton);
  updateButton();

  // Builds an element safely: text is always inserted as text, never as HTML.
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function list(title, items, tone) {
    if (!items || !items.length) return null;
    const box = el("div", "bullets " + tone);
    box.append(el("h4", "", title));
    const ul = el("ul");
    items.forEach((item) => ul.append(el("li", "", item)));
    box.append(ul);
    return box;
  }

  function renderAnswer(a) {
    const card = el("section", "panel answer");
    card.append(el("h3", "", a.title));
    if (a.safety_note) card.append(el("p", "safety", a.safety_note));
    if (a.notice) card.append(el("p", "notice-text", a.notice));
    [list("What your data shows", a.facts, "reef"),
     list("What it could mean", a.interpretations, ""),
     list("What it can't tell you", a.limits, "muted")].forEach((part) => part && card.append(part));
    if (a.related_url) {
      const link = el("a", "link", "Open " + a.related_name + " chart");
      link.href = a.related_url;
      card.append(link);
    }
    card.append(el("p", "muted small source", "Answered by: " + a.source));
    return card;
  }

  async function ask(question) {
    chat.append(el("div", "bubble-user", question));
    const typing = el("div", "panel typing");
    typing.innerHTML = "<i></i><i></i><i></i>";
    chat.append(typing);
    suggestions.hidden = true;
    typing.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "end" });

    let answer;
    try {
      const response = await fetch(form.dataset.url || "/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question }),
      });
      answer = await response.json();
      if (!response.ok) answer = { title: answer.error || "Something went wrong", source: "On-device" };
    } catch {
      answer = { title: "The app couldn't be reached", facts: ["Check that the Velox Health server is still running."], source: "On-device" };
    }
    typing.replaceWith(renderAnswer(answer));
    suggestions.hidden = false;
    chat.lastElementChild.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    updateButton();
    ask(question);
  });

  document.querySelectorAll(".suggestion").forEach((button) =>
    button.addEventListener("click", () => ask(button.dataset.question)));

  // Arrived from an "Ask AI" bar or the AI overview? Ask that question straight away.
  const incoming = new URLSearchParams(location.search).get("q");
  if (incoming && incoming.trim()) {
    history.replaceState(null, "", location.pathname);   // so reloading doesn't ask again
    setTimeout(() => ask(incoming.trim().slice(0, 500)), 450);
  }
}
