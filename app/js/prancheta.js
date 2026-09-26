/* ==========================================================================
   Prancheta: o esquema ilustrativo de uma jogada (posições-modelo da
   formação). Field movido do app.js como está (spec novo-visual, tarefa 4);
   a única mudança é receber teamOf, que antes era global.
   ========================================================================== */
import { isNum } from './ui.js';

const FIELD_W = 53.3;

/**
 * Desenha e anima o tracking real. x do dataset (0–120) vai no eixo
 * vertical e y (0–53.3) no horizontal; quando playDirection é 'left' os
 * eixos são espelhados para o ataque sempre jogar para cima.
 */
export function Field(root, data, teamOf) {
  this.root = root;
  this.data = data;
  this.teamOf = teamOf;
  this.flip = data.playDirection === 'left';
  this.frame = 0;
  this.speed = 1;
  this.timer = null;
  this.selected = null;
  this._viewport();
  this._marks();
  this._dots();
}

Field.prototype._viewport = function () {
  let min = Infinity, max = -Infinity;
  this.data.players.forEach((p) => p.t.forEach((f) => {
    if (!f) return;
    if (f[0] < min) min = f[0];
    if (f[0] > max) max = f[0];
  }));
  if (!isFinite(min)) { min = 20; max = 60; }
  const los = this.data.lineOfScrimmage;
  if (isNum(los)) { min = Math.min(min, los - 2); max = Math.max(max, los + 2); }
  min -= 2.5; max += 2.5;
  if (max - min < 26) { const c = (min + max) / 2; min = c - 13; max = c + 13; }
  this.xMin = Math.max(0, min);
  this.xMax = Math.min(120, max);
};

Field.prototype.pos = function (x, y) {
  const span = this.xMax - this.xMin || 1;
  const t = (x - this.xMin) / span;
  return {
    left: ((this.flip ? FIELD_W - y : y) / FIELD_W) * 100,
    top: (this.flip ? t : 1 - t) * 100,
  };
};

Field.prototype._marks = function () {
  const L = [];
  for (let x = Math.ceil(this.xMin / 5) * 5; x <= this.xMax; x += 5) {
    const top = this.pos(x, 0).top;
    const ten = (x - 10) % 10 === 0;
    const goal = x === 10 || x === 110;
    const yard = x - 10;
    L.push('<line x1="0" y1="' + top + '%" x2="100%" y2="' + top + '%" stroke="rgba(255,255,255,' +
      (goal ? 0.95 : ten ? 0.5 : 0.22) + ')" stroke-width="' + (goal ? 2.5 : ten ? 1.5 : 1) + '"/>');
    if (ten && yard > 0 && yard < 100) {
      const lbl = yard <= 50 ? yard : 100 - yard;
      L.push('<text x="6" y="' + top + '%" dy="-4" font-size="12" font-weight="700" ' +
        'fill="rgba(255,255,255,.6)" font-family="Barlow Condensed,sans-serif">' + lbl + '</text>');
      L.push('<text x="94%" y="' + top + '%" dy="-4" font-size="12" font-weight="700" ' +
        'fill="rgba(255,255,255,.6)" font-family="Barlow Condensed,sans-serif">' + lbl + '</text>');
    }
  }
  const los = this.data.lineOfScrimmage;
  if (isNum(los)) {
    L.push('<line x1="0" y1="' + this.pos(los, 0).top + '%" x2="100%" y2="' +
      this.pos(los, 0).top + '%" stroke="#3B82F6" stroke-width="2.5"/>');
    const ytg = this.data.yardsToGo;
    if (isNum(ytg)) {
      const fd = this.flip ? los - ytg : los + ytg;
      if (fd > this.xMin && fd < this.xMax) {
        L.push('<line x1="0" y1="' + this.pos(fd, 0).top + '%" x2="100%" y2="' +
          this.pos(fd, 0).top + '%" stroke="#FACC15" stroke-width="2" stroke-dasharray="7 5"/>');
      }
    }
  }
  this.root.innerHTML = '<svg class="marks" preserveAspectRatio="none" aria-hidden="true">' +
    L.join('') + '</svg>';
};

Field.prototype._dots = function () {
  this.dots = {};
  const self = this;
  this.data.players.forEach((p) => {
    const def = p.side === 'defense';
    const d = document.createElement('div');
    d.className = 'player-dot' + (p.role === 'Pass' ? ' qb' : '') + (def ? ' def' : '');
    d.style.background = self.teamOf(p.team).primary;
    d.setAttribute('role', 'button');
    d.setAttribute('tabindex', '0');
    d.title = (p.name || '') + ' · ' + (p.linedUp || p.position || '') + ' · #' + (p.jersey || '');
    d.setAttribute('aria-label', d.title);
    d.innerHTML = '<span class="num">' + (p.jersey || '') + '</span>';
    const pick = () => self.select(p.nflId);
    d.addEventListener('click', pick);
    d.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); pick(); }
    });
    self.root.appendChild(d);
    self.dots[p.nflId] = d;
  });
  this.ball = document.createElement('div');
  this.ball.className = 'player-dot ball';
  this.ball.setAttribute('aria-hidden', 'true');
  this.root.appendChild(this.ball);
};

Field.prototype.setFrame = function (i) {
  const d = this.data;
  this.frame = Math.max(0, Math.min(d.frameCount - 1, i));
  for (let k = 0; k < d.players.length; k++) {
    const p = d.players[k];
    const f = p.t[this.frame];
    const dot = this.dots[p.nflId];
    if (!dot) continue;
    if (!f) { dot.style.display = 'none'; continue; }
    dot.style.display = '';
    const q = this.pos(f[0], f[1]);
    dot.style.left = q.left + '%';
    dot.style.top = q.top + '%';
  }
  const b = d.ball[this.frame];
  if (b) {
    const q = this.pos(b[0], b[1]);
    this.ball.style.display = '';
    this.ball.style.left = q.left + '%';
    this.ball.style.top = q.top + '%';
  } else this.ball.style.display = 'none';
  if (this.onFrame) this.onFrame(this.frame);
};

// ids de jogador são texto (gsis: 00-0033077)
Field.prototype.select = function (id) {
  this.selected = this.selected === id ? null : id;
  const sel = this.selected;
  Object.keys(this.dots).forEach((k) => {
    this.dots[k].classList.toggle('selected', k === sel);
    this.dots[k].classList.toggle('dim', sel !== null && k !== sel);
  });
  if (this.onSelect) {
    this.onSelect(sel === null ? null : this.data.players.filter((p) => p.nflId === sel)[0]);
  }
};

Field.prototype.play = function () {
  if (this.timer) return;
  if (this.frame >= this.data.frameCount - 1) this.setFrame(0);
  const self = this;
  this.timer = setInterval(() => {
    if (self.frame >= self.data.frameCount - 1) return self.pause();
    self.setFrame(self.frame + 1);
  }, 100 / this.speed);
  if (this.onState) this.onState(true);
};

Field.prototype.pause = function () {
  clearInterval(this.timer);
  this.timer = null;
  if (this.onState) this.onState(false);
};

Field.prototype.toggle = function () { this.timer ? this.pause() : this.play(); };
Field.prototype.setSpeed = function (s) {
  this.speed = s;
  if (this.timer) { this.pause(); this.play(); }
};
Field.prototype.clockAt = function (i) {
  return ((i === undefined ? this.frame : i) - (this.data.snapIndex || 0)) / (this.data.fps || 10);
};
