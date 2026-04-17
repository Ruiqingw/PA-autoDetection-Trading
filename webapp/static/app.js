const COLORS = {
  bgPrice: "#d3e9cf",
  bgIndicator: "#cfe6c9",
  priceUp: "#22ab94",
  priceDown: "#f23645",
  text: "#20242a",
  textDim: "#66717d",
  priceLabelBg: "#1faa8f",
  priceLabelFg: "#ffffff",
  ema12: "#ff9800",
  ema144: "#2962ff",
  ema169: "#ff5a36",
  ema238: "#f2c94c",
  ema338: "#4caf50",
  border: "#8ea08b",
  structureOverlay: "#b77be3",
};

const state = {
  payload: null,
  payloadCache: new Map(),
  inflightPayloads: new Map(),
  selectedSymbol: "BTC/USD",
  selectedInterval: 60,
  chartMode: "candles",
  selectedIndicators: ["delta", "bid_ask"],
  autoRefresh: false,
  autoTimer: null,
  hoverIndex: null,
  warmingIntervals: new Set(),
};

const CLIENT_CACHE_TTL_MS = 20_000;

const elements = {
  symbolChipLabel: document.getElementById("symbolChipLabel"),
  timeframeButtons: document.getElementById("timeframeButtons"),
  modeButtons: document.getElementById("modeButtons"),
  indicatorsButton: document.getElementById("indicatorsButton"),
  indicatorPopup: document.getElementById("indicatorPopup"),
  refreshButton: document.getElementById("refreshButton"),
  autoButton: document.getElementById("autoButton"),
  statusText: document.getElementById("statusText"),
  chartTitle: document.getElementById("chartTitle"),
  chartContext: document.getElementById("chartContext"),
  openValue: document.getElementById("openValue"),
  highValue: document.getElementById("highValue"),
  lowValue: document.getElementById("lowValue"),
  closeValue: document.getElementById("closeValue"),
  changeValue: document.getElementById("changeValue"),
  ema12: document.getElementById("ema12"),
  ema144: document.getElementById("ema144"),
  ema169: document.getElementById("ema169"),
  ema238: document.getElementById("ema238"),
  ema338: document.getElementById("ema338"),
  watchlistRows: document.getElementById("watchlistRows"),
  setupRows: document.getElementById("setupRows"),
  setupNote: document.getElementById("setupNote"),
  bottomMeta: document.getElementById("bottomMeta"),
  chartCanvas: document.getElementById("chartCanvas"),
};

function formatPrice(value) {
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function formatCompactNumber(value) {
  const numeric = Number(value);
  if (Math.abs(numeric) >= 1_000_000) return `${(numeric / 1_000_000).toFixed(2)}M`;
  if (Math.abs(numeric) >= 1_000) return `${(numeric / 1_000).toFixed(2)}K`;
  if (Math.abs(numeric) >= 1) return numeric.toFixed(2);
  return numeric.toFixed(4);
}

function formatChange(value, percent) {
  const sign = value >= 0 ? "+" : "";
  return {
    value: `${sign}${value.toFixed(2)}`,
    percent: `${sign}${percent.toFixed(2)}%`,
  };
}

function formatIntervalLabel(interval) {
  if (interval < 60) return `${interval}m`;
  if (interval === 1440) return "1d";
  return `${interval / 60}h`;
}

function formatCrosshairTime(isoString) {
  const date = new Date(isoString);
  const year = date.getUTCFullYear();
  const month = String(date.getUTCMonth() + 1).padStart(2, "0");
  const day = String(date.getUTCDate()).padStart(2, "0");
  const hours = String(date.getUTCHours()).padStart(2, "0");
  const minutes = String(date.getUTCMinutes()).padStart(2, "0");
  return `${year}-${month}-${day} ${hours}:${minutes}`;
}

function niceStep(rawStep) {
  if (!Number.isFinite(rawStep) || rawStep <= 0) return 1;
  const exponent = Math.floor(Math.log10(rawStep));
  const fraction = rawStep / 10 ** exponent;
  let niceFraction = 1;
  if (fraction <= 1) niceFraction = 1;
  else if (fraction <= 2) niceFraction = 2;
  else if (fraction <= 2.5) niceFraction = 2.5;
  else if (fraction <= 5) niceFraction = 5;
  else niceFraction = 10;
  return niceFraction * 10 ** exponent;
}

function decimalsForStep(step) {
  if (!Number.isFinite(step) || step <= 0) return 2;
  if (step >= 1000) return 0;
  if (step >= 1) return Math.max(0, Math.min(2, Math.ceil(-Math.log10(step * 0.1))));
  return Math.max(2, Math.min(6, Math.ceil(-Math.log10(step)) + 1));
}

function formatAxisPrice(value, step) {
  const decimals = decimalsForStep(step);
  return Number(value).toLocaleString("en-US", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function buildYAxisTicks(scaleTop, scaleBottom, targetCount = 6) {
  const range = Math.max(scaleTop - scaleBottom, 0.0000001);
  const step = niceStep(range / Math.max(targetCount, 2));
  const ticks = [];
  const firstTick = Math.ceil(scaleBottom / step) * step;
  for (let value = firstTick; value <= scaleTop + step * 0.5; value += step) {
    ticks.push(Number(value.toFixed(10)));
  }
  return { step, ticks };
}

function ema(values, span) {
  if (!values.length) return [];
  const alpha = 2 / (span + 1);
  const result = [values[0]];
  for (const value of values.slice(1)) {
    result.push(alpha * value + (1 - alpha) * result[result.length - 1]);
  }
  return result;
}

function displayMarketName(symbol) {
  const names = {
    "BTC/USD": "Bitcoin / US Dollar",
    "ETH/USD": "Ethereum / US Dollar",
    "SOL/USD": "Solana / US Dollar",
  };
  return names[symbol] ?? symbol.replace("/", " / ");
}

function badgeForSymbol(symbol) {
  if (symbol.startsWith("BTC")) return { text: "B", bg: "#f7931a", fg: "#ffffff" };
  if (symbol.startsWith("ETH")) return { text: "E", bg: "#627eea", fg: "#ffffff" };
  if (symbol.startsWith("SOL")) return { text: "S", bg: "#14f195", fg: "#0f1113" };
  return { text: symbol[0], bg: "#2962ff", fg: "#ffffff" };
}

function blendColor(base, accent, weight) {
  const w = Math.max(0, Math.min(weight, 1));
  const baseRgb = [1, 3, 5].map((i) => parseInt(base.slice(i, i + 2), 16));
  const accentRgb = [1, 3, 5].map((i) => parseInt(accent.slice(i, i + 2), 16));
  const mixed = baseRgb.map((value, index) => Math.round(value + (accentRgb[index] - value) * w));
  return `#${mixed.map((value) => value.toString(16).padStart(2, "0")).join("")}`;
}

function latestSummary(bundle, index = null) {
  const candles = bundle.candles;
  const closes = candles.map((candle) => Number(candle.close));
  const opens = candles.map((candle) => Number(candle.open));
  const highs = candles.map((candle) => Number(candle.high));
  const lows = candles.map((candle) => Number(candle.low));
  const ema12 = ema(closes, 12);
  const ema144 = ema(closes, 144);
  const ema169 = ema(closes, 169);
  const ema238 = ema(closes, 238);
  const ema338 = ema(closes, 338);
  const selectedIndex = Math.max(0, Math.min(index ?? candles.length - 1, candles.length - 1));
  const previousClose = closes[Math.max(0, selectedIndex - 1)] ?? closes[selectedIndex];
  const priceChange = closes[selectedIndex] - previousClose;
  const percentChange = previousClose ? (priceChange / previousClose) * 100 : 0;
  return {
    open: opens[selectedIndex],
    high: highs[selectedIndex],
    low: lows[selectedIndex],
    close: closes[selectedIndex],
    priceChange,
    percentChange,
    ema12: ema12[selectedIndex],
    ema144: ema144[selectedIndex],
    ema169: ema169[selectedIndex],
    ema238: ema238[selectedIndex],
    ema338: ema338[selectedIndex],
  };
}

const PANE_INDICATORS = new Set(["delta", "bid_ask"]);
const OVERLAY_INDICATORS = new Set(["order_block", "fvg"]);

class TradingWebChart {
  constructor(canvas, { onHover, onLeave }) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.onHover = onHover;
    this.onLeave = onLeave;
    this.bundle = null;
    this.featureSeries = [];
    this.footprints = [];
    this.closes = [];
    this.ema12 = [];
    this.ema144 = [];
    this.ema169 = [];
    this.ema238 = [];
    this.ema338 = [];
    this.displayMode = "candles";
    this.selectedIndicators = ["delta", "bid_ask"];
    this.indicatorAreaHeight = 180;
    this.viewLeft = 0;
    this.viewCount = 84;
    this.modeViews = {
      candles: null,
      footprint: null,
    };
    this.dragStartX = null;
    this.dragStartY = null;
    this.dragStartViewLeft = null;
    this.dragStartYCenter = null;
    this.dragStartYRange = null;
    this.yAxisDragging = false;
    this.manualYCenter = null;
    this.manualYRange = null;
    this.resizingDivider = false;
    this.hoverIndex = null;
    this.hoverX = null;
    this.hoverY = null;
    this.raf = null;
    this.logicalWidth = 900;
    this.logicalHeight = 640;

    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
    this.installEvents();
    this.resize();
  }

  installEvents() {
    this.canvas.addEventListener("mousedown", (event) => this.handleMouseDown(event));
    window.addEventListener("mousemove", (event) => this.handleMouseMove(event));
    window.addEventListener("mouseup", () => this.handleMouseUp());
    this.canvas.addEventListener("mouseleave", () => this.handleMouseLeave());
    this.canvas.addEventListener("dblclick", (event) => this.handleDoubleClick(event));
    this.canvas.addEventListener(
      "wheel",
      (event) => {
        event.preventDefault();
        const factor = event.deltaY < 0 ? 0.95 : 1.05;
        if (this.priceAxisContains(event.offsetX, event.offsetY)) {
          this.zoomYAxisAt(event.offsetY, factor);
        } else {
          this.zoomAt(event.offsetX, factor);
        }
      },
      { passive: false },
    );
  }

  resize() {
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.logicalWidth = Math.max(rect.width, 640);
    this.logicalHeight = Math.max(rect.height, 420);
    this.canvas.width = Math.round(this.logicalWidth * dpr);
    this.canvas.height = Math.round(this.logicalHeight * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.updateCursor();
    this.requestDraw();
  }

  setBundle(bundle) {
    this.bundle = bundle;
    this.featureSeries = bundle.candle_feature_series;
    this.footprints = bundle.candle_footprints;
    this.closes = bundle.candles.map((candle) => Number(candle.close));
    this.ema12 = ema(this.closes, 12);
    this.ema144 = ema(this.closes, 144);
    this.ema169 = ema(this.closes, 169);
    this.ema238 = ema(this.closes, 238);
    this.ema338 = ema(this.closes, 338);
    this.hoverIndex = null;
    this.hoverX = null;
    this.hoverY = null;
    this.manualYCenter = null;
    this.manualYRange = null;
    this.resetView();
    this.modeViews.candles = { viewLeft: this.viewLeft, viewCount: this.viewCount };
    this.modeViews.footprint = null;
    this.applyDefaultViewForMode();
    this.requestDraw();
  }

  setDisplayMode(mode) {
    if (!["candles", "footprint"].includes(mode)) return;
    if (this.displayMode === mode) return;
    this.storeViewForMode(this.displayMode);
    this.displayMode = mode;
    this.applyDefaultViewForMode();
    this.requestDraw();
  }

  setSelectedIndicators(indicators) {
    const previous = new Set(this.selectedIndicators);
    this.selectedIndicators = [...new Set(indicators)];
    if (this.paneIndicators().length) {
      this.indicatorAreaHeight = Math.max(this.indicatorAreaHeight, 120);
    }
    if (this.selectedIndicators.includes("delta") && !previous.has("delta")) {
      this.focusTradeCoverage();
    }
    this.requestDraw();
  }

  paneIndicators() {
    return this.selectedIndicators.filter((indicator) => PANE_INDICATORS.has(indicator));
  }

  overlayIndicators() {
    return this.selectedIndicators.filter((indicator) => OVERLAY_INDICATORS.has(indicator));
  }

  focusTradeCoverage() {
    if (!this.bundle) return;
    const tradedIndices = this.featureSeries
      .map((point, index) => ({ point, index }))
      .filter(({ point }) => point.trade_count > 0)
      .map(({ index }) => index);
    if (!tradedIndices.length) return;
    const start = tradedIndices[0];
    const end = tradedIndices[tradedIndices.length - 1];
    const span = Math.max(end - start + 1, 1);
    const targetCount = Math.max(28, Math.min(64, span * 2.4));
    const rightOffset = Math.max(4, targetCount * 0.14);
    const center = (start + end) / 2;
    const targetLeft = center - targetCount / 2 + rightOffset * 0.35;
    this.viewCount = Math.min(targetCount, this.bundle.candles.length + 40);
    this.viewLeft = this.clampViewLeft(targetLeft);
    this.storeViewForMode(this.displayMode);
  }

  storeViewForMode(mode) {
    if (!this.bundle || !["candles", "footprint"].includes(mode)) return;
    this.modeViews[mode] = {
      viewLeft: this.viewLeft,
      viewCount: this.viewCount,
    };
  }

  applyDefaultViewForMode() {
    if (!this.bundle) return;
    const savedView = this.modeViews[this.displayMode];
    if (savedView) {
      this.viewCount = savedView.viewCount;
      this.viewLeft = this.clampViewLeft(savedView.viewLeft);
      if (this.displayMode === "candles" && this.actualVisibleIndices().length) {
        return;
      }
    }

    if (this.displayMode === "footprint") {
      const rightEdge = this.viewLeft + this.viewCount;
      this.viewCount = 12;
      this.viewLeft = this.clampViewLeft(rightEdge - this.viewCount);
      this.storeViewForMode("footprint");
      return;
    }

    this.resetView();
    this.storeViewForMode("candles");
  }

  resetView() {
    if (!this.bundle) return;
    this.viewCount = Math.min(Math.max(this.bundle.candles.length, 40), 84);
    const rightOffset = Math.max(this.viewCount * 0.12, 6);
    this.viewLeft = Math.max(0, this.bundle.candles.length - this.viewCount + rightOffset);
    this.viewLeft = Math.min(this.viewLeft, this.maxViewLeft());
  }

  plotGeometry() {
    const width = Math.max(this.logicalWidth, 640);
    const height = Math.max(this.logicalHeight, 420);
    const left = 18;
    const right = width - 92;
    const top = 24;
    const bottom = height - 26;
    const indicatorHeight = this.paneIndicators().length ? Math.min(this.indicatorAreaHeight, height * 0.5) : 0;
    const indicatorTop = indicatorHeight ? bottom - indicatorHeight : bottom;
    const priceBottom = this.paneIndicators().length ? indicatorTop - 10 : bottom;
    return { width, height, left, right, top, bottom, indicatorTop, priceBottom };
  }

  candleSpace() {
    const { left, right } = this.plotGeometry();
    return Math.max((right - left) / Math.max(this.viewCount, 1), 1);
  }

  maxViewLeft() {
    if (!this.bundle) return 0;
    const futureSpace = Math.max(24, this.viewCount * 0.95);
    return Math.max(0, this.bundle.candles.length - this.viewCount + futureSpace);
  }

  clampViewLeft(value) {
    return Math.max(0, Math.min(value, this.maxViewLeft()));
  }

  visibleIndices() {
    if (!this.bundle) return [];
    const start = Math.max(0, Math.floor(this.viewLeft) - 1);
    const end = Math.min(this.bundle.candles.length - 1, Math.ceil(this.viewLeft + this.viewCount) + 1);
    return Array.from({ length: end - start + 1 }, (_, index) => start + index);
  }

  actualVisibleIndices() {
    if (!this.bundle) return [];
    const leftEdge = this.viewLeft;
    const rightEdge = this.viewLeft + this.viewCount;
    return this.bundle.candles
      .map((_, index) => index)
      .filter((index) => leftEdge <= index && index <= rightEdge);
  }

  xFromIndex(index) {
    const { left } = this.plotGeometry();
    return left + ((index - this.viewLeft) + 0.5) * this.candleSpace();
  }

  indexFromX(x) {
    if (!this.bundle) return null;
    const { left, right } = this.plotGeometry();
    if (x < left || x > right) return null;
    const index = Math.round(this.viewLeft + ((x - left) / this.candleSpace()) - 0.5);
    return index >= 0 && index < this.bundle.candles.length ? index : null;
  }

  plotContains(x, y) {
    const { left, right, top, priceBottom } = this.plotGeometry();
    return left <= x && x <= right && top <= y && y <= priceBottom;
  }

  priceAxisContains(x, y) {
    const { right, width, top, priceBottom } = this.plotGeometry();
    return right < x && x <= width && top <= y && y <= priceBottom;
  }

  dividerHit(y) {
    if (!this.paneIndicators().length) return false;
    const { indicatorTop } = this.plotGeometry();
    return Math.abs(y - indicatorTop) <= 6;
  }

  updateCursor(x = this.hoverX, y = this.hoverY) {
    let cursor = "default";
    if (this.resizingDivider) cursor = "row-resize";
    else if (this.yAxisDragging) cursor = "ns-resize";
    else if (x !== null && y !== null) {
      if (this.priceAxisContains(x, y)) cursor = "ns-resize";
      else if (this.dividerHit(y)) cursor = "row-resize";
      else if (this.plotContains(x, y)) cursor = "crosshair";
    }
    this.canvas.style.cursor = cursor;
  }

  requestDraw() {
    if (this.raf !== null) return;
    this.raf = window.requestAnimationFrame(() => {
      this.raf = null;
      this.redraw();
    });
  }

  handleMouseDown(event) {
    if (!this.bundle) return;
    const { left, top } = this.canvas.getBoundingClientRect();
    const x = event.clientX - left;
    const y = event.clientY - top;
    if (this.dividerHit(y)) {
      this.resizingDivider = true;
      this.clearHover(true);
      this.updateCursor(x, y);
      this.requestDraw();
      return;
    }
    if (this.priceAxisContains(x, y)) {
      const activeScale = this.currentYScale();
      this.yAxisDragging = true;
      this.dragStartY = y;
      this.dragStartYCenter = activeScale.center;
      this.dragStartYRange = activeScale.range;
      this.clearHover(true);
      this.updateCursor(x, y);
      this.requestDraw();
      return;
    }
    this.dragStartX = x;
    this.dragStartY = y;
    this.dragStartViewLeft = this.viewLeft;
    if (this.manualYRange !== null && this.manualYCenter !== null) {
      this.dragStartYCenter = this.manualYCenter;
      this.dragStartYRange = this.manualYRange;
    } else {
      const activeScale = this.currentYScale();
      this.dragStartYCenter = activeScale.center;
      this.dragStartYRange = activeScale.range;
    }
    this.clearHover(true);
    this.updateCursor(x, y);
    this.requestDraw();
  }

  handleMouseMove(event) {
    if (!this.bundle) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (this.resizingDivider) {
      const { top, bottom, height } = this.plotGeometry();
      const minHeight = 90;
      const maxHeight = Math.max(Math.min(height * 0.5, height - top - 80), minHeight);
      this.indicatorAreaHeight = Math.max(minHeight, Math.min(maxHeight, bottom - y));
      this.updateCursor(x, y);
      this.requestDraw();
      return;
    }
    if (this.yAxisDragging && this.dragStartY !== null && this.dragStartYRange !== null) {
      const deltaPixels = y - this.dragStartY;
      const factor = Math.exp(deltaPixels / 180);
      const autoScale = this.computeAutoScale();
      const minRange = Math.max(autoScale.range * 0.12, 0.0001);
      const maxRange = autoScale.range * 8;
      this.manualYRange = Math.max(minRange, Math.min(maxRange, this.dragStartYRange * factor));
      this.manualYCenter = this.dragStartYCenter ?? autoScale.center;
      this.updateCursor(x, y);
      this.requestDraw();
      return;
    }
    if (this.dragStartX !== null && this.dragStartViewLeft !== null) {
      const deltaPixels = x - this.dragStartX;
      this.viewLeft = this.clampViewLeft(this.dragStartViewLeft - deltaPixels / this.candleSpace());
      if (this.manualYRange !== null && this.dragStartY !== null && this.dragStartYCenter !== null && this.dragStartYRange !== null) {
        const { top, priceBottom } = this.plotGeometry();
        const usableHeight = Math.max(priceBottom - top - 12, 1);
        const deltaY = y - this.dragStartY;
        const centerShift = (deltaY / usableHeight) * this.dragStartYRange;
        this.manualYCenter = this.dragStartYCenter + centerShift;
      }
      this.updateCursor(x, y);
      this.requestDraw();
      return;
    }
    this.updateHover(x, y);
    this.updateCursor(x, y);
  }

  handleMouseUp() {
    if (this.dragStartX !== null || this.resizingDivider || this.yAxisDragging) {
      this.storeViewForMode(this.displayMode);
    }
    this.yAxisDragging = false;
    this.resizingDivider = false;
    this.dragStartX = null;
    this.dragStartY = null;
    this.dragStartViewLeft = null;
    this.dragStartYCenter = null;
    this.dragStartYRange = null;
    this.updateCursor();
  }

  handleMouseLeave() {
    this.clearHover(false);
    if (this.onLeave) this.onLeave();
    this.updateCursor(null, null);
    this.requestDraw();
  }

  clearHover(notify) {
    const previous = this.hoverIndex;
    this.hoverIndex = null;
    this.hoverX = null;
    this.hoverY = null;
    if (notify && previous !== null && this.onHover) {
      this.onHover(null);
    }
  }

  updateHover(x, y) {
    if (!this.plotContains(x, y)) {
      this.clearHover(true);
      this.requestDraw();
      return;
    }
    const index = this.indexFromX(x);
    const snappedX = index === null ? x : this.xFromIndex(index);
    const positionChanged = this.hoverX !== snappedX || this.hoverY !== y;
    const indexChanged = index !== this.hoverIndex;
    this.hoverX = snappedX;
    this.hoverY = y;
    this.hoverIndex = index;
    if (indexChanged && this.onHover) this.onHover(index);
    if (positionChanged || indexChanged) this.requestDraw();
  }

  zoomAt(x, factor) {
    if (!this.bundle) return;
    const { left, right } = this.plotGeometry();
    if (x < left || x > right) return;
    const relative = (x - left) / Math.max(right - left, 1);
    const anchor = this.viewLeft + relative * this.viewCount;
    const newCount = Math.max(24, Math.min(this.bundle.candles.length + 40, this.viewCount * factor));
    this.viewLeft = this.clampViewLeft(anchor - relative * newCount);
    this.viewCount = newCount;
    this.storeViewForMode(this.displayMode);
    this.requestDraw();
  }

  computeAutoScale() {
    if (!this.bundle) {
      return {
        top: 1,
        bottom: 0,
        range: 1,
        center: 0.5,
      };
    }
    const actualVisible = this.actualVisibleIndices();
    if (!actualVisible.length) {
      return {
        top: 1,
        bottom: 0,
        range: 1,
        center: 0.5,
      };
    }
    const highs = actualVisible.map((index) => Number(this.bundle.candles[index].high));
    const lows = actualVisible.map((index) => Number(this.bundle.candles[index].low));
    const emaVisible = [
      this.ema12,
      this.ema144,
      this.ema169,
      this.ema238,
      this.ema338,
    ]
      .flatMap((series) => actualVisible.map((index) => series[index]))
      .filter((value) => Number.isFinite(value));
    const minPrice = Math.min(...lows, ...emaVisible);
    const maxPrice = Math.max(...highs, ...emaVisible);
    const priceRange = Math.max(maxPrice - minPrice, 1);
    const yPadTop = priceRange * 0.14;
    const yPadBottom = priceRange * 0.18;
    const top = maxPrice + yPadTop;
    const bottom = minPrice - yPadBottom;
    const range = Math.max(top - bottom, 0.0001);
    return {
      top,
      bottom,
      range,
      center: (top + bottom) / 2,
    };
  }

  currentYScale() {
    const autoScale = this.computeAutoScale();
    if (this.manualYCenter === null || this.manualYRange === null) {
      return autoScale;
    }
    const range = Math.max(this.manualYRange, 0.0001);
    const center = this.manualYCenter;
    return {
      top: center + range / 2,
      bottom: center - range / 2,
      range,
      center,
    };
  }

  zoomYAxisAt(y, factor) {
    if (!this.bundle) return;
    const { top, priceBottom } = this.plotGeometry();
    const usableHeight = Math.max(priceBottom - top - 12, 1);
    const clampedY = Math.max(top + 12, Math.min(priceBottom, y));
    const normalized = (clampedY - (top + 12)) / usableHeight;
    const scale = this.currentYScale();
    const anchorPrice = scale.top - normalized * scale.range;
    const autoScale = this.computeAutoScale();
    const minRange = Math.max(autoScale.range * 0.12, 0.0001);
    const maxRange = autoScale.range * 8;
    const nextRange = Math.max(minRange, Math.min(maxRange, scale.range * factor));
    const center = anchorPrice - nextRange * (0.5 - normalized);
    this.manualYRange = nextRange;
    this.manualYCenter = center;
    this.requestDraw();
  }

  resetYAxisScale() {
    this.manualYCenter = null;
    this.manualYRange = null;
    this.requestDraw();
  }

  handleDoubleClick(event) {
    if (!this.bundle) return;
    const rect = this.canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    if (this.plotContains(x, y) || this.priceAxisContains(x, y)) {
      this.resetYAxisScale();
    }
  }

  drawTextBox(ctx, x, y, text, { anchor = "w", fill = COLORS.text, bg = "#ffffff", outline = "", font = "10px Helvetica", padX = 8, padY = 4 }) {
    ctx.save();
    ctx.font = font;
    const metrics = ctx.measureText(text);
    const width = metrics.width;
    const height = parseInt(font, 10) || 10;
    let boxX = x;
    if (anchor === "e") boxX = x - width - padX * 2;
    if (anchor === "center") boxX = x - width / 2 - padX;
    if (anchor === "w") boxX = x;
    const boxY = y - height / 2 - padY;
    const boxWidth = width + padX * 2;
    const boxHeight = height + padY * 2;
    ctx.fillStyle = bg;
    ctx.fillRect(boxX, boxY, boxWidth, boxHeight);
    if (outline) {
      ctx.strokeStyle = outline;
      ctx.strokeRect(boxX + 0.5, boxY + 0.5, boxWidth - 1, boxHeight - 1);
    }
    ctx.fillStyle = fill;
    ctx.textBaseline = "middle";
    ctx.textAlign = anchor === "e" ? "right" : anchor === "center" ? "center" : "left";
    const textX = anchor === "e" ? boxX + boxWidth - padX : anchor === "center" ? boxX + boxWidth / 2 : boxX + padX;
    ctx.fillText(text, textX, y);
    ctx.restore();
  }

  drawLineSeries(ctx, indices, values, yFn, color, width = 2) {
    if (indices.length < 2) return;
    ctx.save();
    ctx.beginPath();
    indices.forEach((index, idx) => {
      const x = this.xFromIndex(index);
      const y = yFn(values[index]);
      if (idx === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.stroke();
    ctx.restore();
  }

  drawCandles(ctx, indices, yPrice, bodyWidth, priceBottom, maxVolume, volumeHeight) {
    indices.forEach((index) => {
      const candle = this.bundle.candles[index];
      const x = this.xFromIndex(index);
      const open = Number(candle.open);
      const high = Number(candle.high);
      const low = Number(candle.low);
      const close = Number(candle.close);
      const color = close >= open ? COLORS.priceUp : COLORS.priceDown;
      const yOpen = yPrice(open);
      const yClose = yPrice(close);
      const yHigh = yPrice(high);
      const yLow = yPrice(low);
      const top = Math.min(yOpen, yClose);
      const bottom = Math.max(yOpen, yClose);

      ctx.save();
      ctx.strokeStyle = color;
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(x, yHigh);
      ctx.lineTo(x, yLow);
      ctx.stroke();
      ctx.fillStyle = color;
      ctx.fillRect(x - bodyWidth / 2, top, bodyWidth, Math.max(bottom - top, 2));

      const volume = Number(candle.volume);
      const barHeight = maxVolume ? (volume / maxVolume) * volumeHeight : 0;
      ctx.fillStyle = close >= open ? "#a4ddd1" : "#e8c6c0";
      ctx.fillRect(x - bodyWidth / 2, priceBottom - 10 - barHeight, bodyWidth, barHeight);
      ctx.restore();
    });
  }

  drawFootprints(ctx, indices, yPrice, bodyWidth, priceBottom, maxVolume, volumeHeight) {
    const neutralBg = "#dfe7da";
    const outline = "#8ea08b";
    indices.forEach((index) => {
      const candle = this.bundle.candles[index];
      const footprint = this.footprints[index];
      const x = this.xFromIndex(index);
      const highY = yPrice(Number(candle.high));
      const lowY = yPrice(Number(candle.low));
      const openY = yPrice(Number(candle.open));
      const closeY = yPrice(Number(candle.close));
      const boxWidth = Math.min(Math.max(bodyWidth * 1.08, 14), Math.max(this.candleSpace() * 0.82, 14));
      const leftX = x - boxWidth / 2;
      const rightX = x + boxWidth / 2;
      const midX = x;
      const delta = footprint?.normalized_delta ?? 0;
      const borderColor = blendColor(outline, delta >= 0 ? COLORS.priceUp : COLORS.priceDown, 0.35);
      const hasPriceLevels = footprint && footprint.price_levels.length >= 2;
      const canRenderCells = hasPriceLevels && boxWidth >= 34;

      if (canRenderCells) {
        ctx.save();
        ctx.strokeStyle = borderColor;
        ctx.strokeRect(leftX, highY, boxWidth, lowY - highY);
        const maxLevelVolume = Math.max(...footprint.price_levels.map((level) => Number(level.total_volume)), 1);
        footprint.price_levels.forEach((level) => {
          const rowTop = yPrice(Math.min(Number(level.upper_price), Number(candle.high)));
          const rowBottom = Math.max(yPrice(Math.max(Number(level.lower_price), Number(candle.low))), rowTop + 2);
          const levelScale = Number(level.total_volume) / maxLevelVolume;
          const sellFill = blendColor(neutralBg, COLORS.priceDown, 0.06 + levelScale * 0.12 + Math.abs(Math.min(level.normalized_delta, 0)) * 0.34);
          const buyFill = blendColor(neutralBg, COLORS.priceUp, 0.06 + levelScale * 0.12 + Math.max(level.normalized_delta, 0) * 0.34);
          ctx.fillStyle = sellFill;
          ctx.fillRect(leftX + 1, rowTop, boxWidth / 2 - 1, rowBottom - rowTop);
          ctx.fillStyle = buyFill;
          ctx.fillRect(midX, rowTop, boxWidth / 2 - 1, rowBottom - rowTop);
          ctx.strokeStyle = "#c9d5c4";
          ctx.beginPath();
          ctx.moveTo(leftX + 1, rowBottom);
          ctx.lineTo(rightX - 1, rowBottom);
          ctx.stroke();
        });
        ctx.strokeStyle = borderColor;
        ctx.beginPath();
        ctx.moveTo(midX, highY + 2);
        ctx.lineTo(midX, lowY - 2);
        ctx.stroke();
        ctx.strokeStyle = "#4e575f";
        ctx.beginPath();
        ctx.moveTo(leftX, openY);
        ctx.lineTo(rightX, openY);
        ctx.stroke();
        ctx.strokeStyle = Number(candle.close) >= Number(candle.open) ? COLORS.priceUp : COLORS.priceDown;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(leftX, closeY);
        ctx.lineTo(rightX, closeY);
        ctx.stroke();
        ctx.restore();
      } else {
        const candleColor = Number(candle.close) >= Number(candle.open) ? COLORS.priceUp : COLORS.priceDown;
        ctx.save();
        ctx.strokeStyle = "#91a296";
        ctx.beginPath();
        ctx.moveTo(x, highY);
        ctx.lineTo(x, lowY);
        ctx.stroke();
        ctx.strokeStyle = blendColor("#9fb3aa", candleColor, 0.45);
        const bodyLeft = x - Math.max(bodyWidth * 0.42, 2);
        const bodyRight = x + Math.max(bodyWidth * 0.42, 2);
        const bodyTop = Math.min(openY, closeY);
        const bodyHeight = Math.max(Math.abs(closeY - openY), 2);
        ctx.strokeRect(bodyLeft, bodyTop, bodyRight - bodyLeft, bodyHeight);
        ctx.restore();
      }

      const volume = footprint && Number(footprint.total_volume) > 0 ? Number(footprint.total_volume) : Number(candle.volume);
      const barHeight = maxVolume ? (volume / maxVolume) * volumeHeight : 0;
      ctx.fillStyle = blendColor("#dfe7da", delta >= 0 ? COLORS.priceUp : COLORS.priceDown, 0.38);
      ctx.fillRect(x - bodyWidth / 2, priceBottom - 10 - barHeight, bodyWidth, barHeight);
    });
  }

  drawDeltaIndicator(ctx, indices, left, right, paneTop, paneBottom, bodyWidth) {
    const values = indices.map((index) => this.featureSeries[index].normalized_delta * 100);
    const covered = indices.filter((index) => this.featureSeries[index].trade_count > 0);
    const maxAbs = Math.max(...values.map((value) => Math.abs(value)), 10);
    const midY = (paneTop + paneBottom) / 2;
    ctx.save();
    ctx.strokeStyle = "#b7c2b1";
    ctx.setLineDash([4, 6]);
    ctx.beginPath();
    ctx.moveTo(left, midY);
    ctx.lineTo(right, midY);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = COLORS.textDim;
    ctx.font = "10px Helvetica";
    ctx.fillText("Delta", left, paneTop + 12);
    ctx.textAlign = "right";
    ctx.fillText(`${covered.length}/${indices.length} candles covered`, right, paneTop + 12);
    ctx.textAlign = "left";
    if (!covered.length) {
      ctx.textAlign = "center";
      ctx.font = "11px Helvetica";
      ctx.fillText("No captured trades in current view", (left + right) / 2, (paneTop + paneBottom) / 2);
      ctx.restore();
      return;
    }
    const usableHeight = Math.max((paneBottom - paneTop) / 2 - 18, 1);
    covered.forEach((index) => {
      const value = this.featureSeries[index].normalized_delta * 100;
      const x = this.xFromIndex(index);
      const barHeight = (Math.abs(value) / maxAbs) * usableHeight;
      ctx.fillStyle = value >= 0 ? COLORS.priceUp : COLORS.priceDown;
      ctx.fillRect(x - bodyWidth / 2, value >= 0 ? midY - barHeight : midY, bodyWidth, barHeight);
    });
    ctx.restore();
  }

  drawBidAskIndicator(ctx, left, right, paneTop, paneBottom) {
    const indicator = this.bundle.analysis.bid_ask_indicator;
    ctx.save();
    ctx.fillStyle = COLORS.textDim;
    ctx.font = "10px Helvetica";
    ctx.fillText("Bid / Ask", left, paneTop + 12);
    if (!indicator) {
      ctx.font = "11px Helvetica";
      ctx.fillText("No book snapshot", left + 80, (paneTop + paneBottom) / 2);
      ctx.restore();
      return;
    }
    const centerX = (left + right) / 2;
    const paneHeight = paneBottom - paneTop;
    const gaugeY = paneTop + Math.max(32, Math.min(42, paneHeight * 0.38));
    const gaugeHeight = 16;
    const gaugeHalfWidth = Math.min((right - left) * 0.32, 180);
    const imbalance = Number(indicator.top_of_book_imbalance);
    const fillWidth = gaugeHalfWidth * Math.abs(imbalance);
    ctx.fillStyle = "#dfe7da";
    ctx.strokeStyle = "#b7c2b1";
    ctx.fillRect(centerX - gaugeHalfWidth, gaugeY, gaugeHalfWidth * 2, gaugeHeight);
    ctx.strokeRect(centerX - gaugeHalfWidth, gaugeY, gaugeHalfWidth * 2, gaugeHeight);
    ctx.strokeStyle = "#8ea08b";
    ctx.beginPath();
    ctx.moveTo(centerX, gaugeY - 4);
    ctx.lineTo(centerX, gaugeY + gaugeHeight + 4);
    ctx.stroke();
    ctx.fillStyle = imbalance >= 0 ? COLORS.priceUp : COLORS.priceDown;
    if (imbalance >= 0) {
      ctx.fillRect(centerX, gaugeY + 1, fillWidth, gaugeHeight - 2);
    } else {
      ctx.fillRect(centerX - fillWidth, gaugeY + 1, fillWidth, gaugeHeight - 2);
    }
    const bidText = `Bid ${Number(indicator.best_bid_volume).toFixed(2)}`;
    const askText = `Ask ${Number(indicator.best_ask_volume).toFixed(2)}`;
    const ratio = indicator.bid_ask_volume_ratio === null ? "N/A" : `${Number(indicator.bid_ask_volume_ratio).toFixed(2)}x`;
    const spreadText = `Spread ${Number(indicator.spread).toFixed(2)} / ${Number(indicator.spread_bps).toFixed(2)}bps`;
    const footerY = Math.max(paneTop + 54, paneBottom - 26);
    const metricsY = Math.min(footerY - 12, gaugeY + gaugeHeight + 20);
    ctx.font = "10px Helvetica";
    ctx.fillStyle = COLORS.priceUp;
    ctx.textAlign = "left";
    ctx.fillText(bidText, left, footerY);
    ctx.fillStyle = COLORS.text;
    ctx.textAlign = "center";
    ctx.fillText(`Ratio ${ratio}`, centerX, footerY);
    ctx.fillStyle = COLORS.priceDown;
    ctx.textAlign = "right";
    ctx.fillText(askText, right, footerY);
    ctx.fillStyle = COLORS.textDim;
    ctx.textAlign = "center";
    ctx.fillText(spreadText, centerX, metricsY);
    ctx.restore();
  }

  drawStructureZones(ctx, visible, yPrice, bodyWidth, priceBottom) {
    if (![60, 240, 1440].includes(this.bundle.interval_minutes)) return;
    const activeKinds = new Set(this.overlayIndicators());
    if (!activeKinds.size) return;

    const openIndex = new Map(this.bundle.candles.map((candle, index) => [candle.open_time, index]));
    const closeIndex = new Map(this.bundle.candles.map((candle, index) => [candle.close_time, index]));

    this.bundle.structure_zones
      .filter((zone) => activeKinds.has(zone.kind) && !(zone.kind === "fvg" && zone.mitigated))
      .forEach((zone) => {
        const startIndex = openIndex.get(zone.start_time);
        const endIndex = closeIndex.get(zone.end_time) ?? this.bundle.candles.length - 1;
        if (startIndex === undefined) return;
        if (endIndex < visible[0] || startIndex > visible[visible.length - 1]) return;

        const clampedStart = Math.max(startIndex, visible[0]);
        const clampedEnd = Math.min(endIndex, visible[visible.length - 1]);
        const leftX = this.xFromIndex(clampedStart) - bodyWidth * 0.9;
        const rightX = this.xFromIndex(clampedEnd) + bodyWidth * 0.9;
        const zoneTop = Math.max(24, yPrice(zone.upper_price));
        const zoneBottom = Math.min(priceBottom - 2, yPrice(zone.lower_price));
        const zoneHeight = Math.max(zoneBottom - zoneTop, 3);
        const labelY = Math.max(zoneTop + 11, Math.min(zoneBottom - 6, zoneTop + 14));

        ctx.save();
        ctx.fillStyle = COLORS.structureOverlay;
        ctx.globalAlpha = zone.kind === "fvg" ? 0.11 : 0.15;
        ctx.fillRect(leftX, zoneTop, Math.max(rightX - leftX, 4), zoneHeight);
        ctx.globalAlpha = 1;
        ctx.strokeStyle = COLORS.structureOverlay;
        ctx.lineWidth = zone.kind === "fvg" ? 1.2 : 1.6;
        if (zone.kind === "fvg") ctx.setLineDash([6, 4]);
        ctx.strokeRect(leftX + 0.5, zoneTop + 0.5, Math.max(rightX - leftX - 1, 3), Math.max(zoneHeight - 1, 2));
        ctx.setLineDash([]);
        ctx.fillStyle = COLORS.structureOverlay;
        ctx.font = "bold 10px Helvetica";
        ctx.textAlign = "left";
        ctx.fillText(zone.label, leftX + 6, labelY);
        ctx.font = "9px Helvetica";
        ctx.fillText(zone.side === "bullish" ? "B" : "S", leftX + 28, labelY);
        ctx.restore();
      });
  }

  drawIndicatorPanes(ctx, indices, left, right, indicatorTop, bottom, bodyWidth, width) {
    const paneIndicators = this.paneIndicators();
    if (!paneIndicators.length) return;
    ctx.save();
    ctx.fillStyle = COLORS.bgIndicator;
    ctx.fillRect(0, indicatorTop, width, bottom + 8 - indicatorTop);
    ctx.strokeStyle = "#a8b7a2";
    ctx.beginPath();
    ctx.moveTo(0, indicatorTop + 0.5);
    ctx.lineTo(width, indicatorTop + 0.5);
    ctx.stroke();
    const paneHeight = (bottom - indicatorTop) / paneIndicators.length;
    paneIndicators.forEach((indicatorName, paneIndex) => {
      const paneTop = indicatorTop + paneIndex * paneHeight;
      const paneBottom = indicatorTop + (paneIndex + 1) * paneHeight;
      if (paneIndex > 0) {
        ctx.strokeStyle = "#b7c2b1";
        ctx.beginPath();
        ctx.moveTo(0, paneTop + 0.5);
        ctx.lineTo(width, paneTop + 0.5);
        ctx.stroke();
      }
      if (indicatorName === "delta") this.drawDeltaIndicator(ctx, indices, left, right, paneTop, paneBottom, bodyWidth);
      if (indicatorName === "bid_ask") this.drawBidAskIndicator(ctx, left, right, paneTop, paneBottom);
    });
    ctx.restore();
  }

  redraw() {
    const ctx = this.ctx;
    const { width, height, left, right, top, bottom, indicatorTop, priceBottom } = this.plotGeometry();
    ctx.clearRect(0, 0, width, height);
    if (!this.bundle || !this.bundle.candles.length) return;

    ctx.fillStyle = COLORS.bgPrice;
    ctx.fillRect(0, 0, width, priceBottom);

    const visible = this.visibleIndices();
    const actualVisible = this.actualVisibleIndices();
    if (!actualVisible.length) return;
    const activeScale = this.currentYScale();
    const scaleTop = activeScale.top;
    const scaleBottom = activeScale.bottom;
    const scaleRange = activeScale.range;
    const volumeHeight = 90;
    const yPrice = (value) => {
      const usableHeight = priceBottom - top - 12;
      return top + 12 + ((scaleTop - value) / scaleRange) * usableHeight;
    };
    const priceFromY = (y) => {
      const usableHeight = priceBottom - top - 12;
      const clampedY = Math.max(top + 12, Math.min(priceBottom, y));
      const normalized = (clampedY - (top + 12)) / Math.max(usableHeight, 1);
      return scaleTop - normalized * scaleRange;
    };

    const candleSpace = this.candleSpace();
    const bodyWidth = Math.max(candleSpace * 0.62, 2);
    const maxVolume = this.displayMode === "footprint"
      ? Math.max(...this.footprints.map((item) => Number(item?.total_volume ?? 0)), 1)
      : Math.max(...this.bundle.candles.map((candle) => Number(candle.volume)), 1);

    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, width, priceBottom);
    ctx.clip();

    const supportLevel = this.bundle.analysis.signal ? Number(this.bundle.analysis.signal.support_level) : null;
    if (supportLevel !== null) {
      ctx.save();
      ctx.strokeStyle = "#6b6f74";
      ctx.beginPath();
      ctx.moveTo(left, yPrice(supportLevel));
      ctx.lineTo(right, yPrice(supportLevel));
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.fillStyle = "#9aa998";
    ctx.globalAlpha = 0.32;
    ctx.font = "56px Helvetica";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(`${this.bundle.symbol.replace("/", "")}, ${this.bundle.interval_label}`, (left + right) / 2, top + (priceBottom - top) * 0.52);
    ctx.restore();

    this.drawStructureZones(ctx, visible, yPrice, bodyWidth, priceBottom);
    if (this.displayMode === "footprint") {
      this.drawFootprints(ctx, visible, yPrice, bodyWidth, priceBottom, maxVolume, volumeHeight);
    } else {
      this.drawCandles(ctx, visible, yPrice, bodyWidth, priceBottom, maxVolume, volumeHeight);
    }

    this.drawLineSeries(ctx, visible, this.ema12, yPrice, COLORS.ema12, 2);
    this.drawLineSeries(ctx, visible, this.ema144, yPrice, COLORS.ema144, 2);
    this.drawLineSeries(ctx, visible, this.ema169, yPrice, COLORS.ema169, 2);
    this.drawLineSeries(ctx, visible, this.ema238, yPrice, COLORS.ema238, 2);
    this.drawLineSeries(ctx, visible, this.ema338, yPrice, COLORS.ema338, 2);

    ctx.restore();

    const yAxisTicks = buildYAxisTicks(scaleTop, scaleBottom, 6);
    ctx.save();
    ctx.fillStyle = COLORS.textDim;
    ctx.font = "10px Helvetica";
    ctx.textAlign = "right";
    yAxisTicks.ticks.forEach((value) => {
      const yTick = yPrice(value);
      ctx.strokeStyle = "#c4d1bf";
      ctx.globalAlpha = 0.5;
      ctx.beginPath();
      ctx.moveTo(left, yTick);
      ctx.lineTo(right, yTick);
      ctx.stroke();
      ctx.globalAlpha = 1;
      ctx.fillText(formatAxisPrice(value, yAxisTicks.step), width - 12, yTick + 4);
    });
    ctx.restore();

    const currentClose = Number(this.bundle.candles[this.bundle.candles.length - 1].close);
    const yCurrent = yPrice(currentClose);
    ctx.save();
    ctx.strokeStyle = "#9fb3aa";
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(left, yCurrent);
    ctx.lineTo(right, yCurrent);
    ctx.stroke();
    ctx.restore();
    this.drawTextBox(ctx, right + 6, yCurrent, formatPrice(currentClose), {
      anchor: "w",
      fill: COLORS.priceLabelFg,
      bg: COLORS.priceLabelBg,
      font: "bold 10px Helvetica",
    });

    const highIndex = actualVisible.reduce((best, index) => Number(this.bundle.candles[index].high) > Number(this.bundle.candles[best].high) ? index : best, actualVisible[0]);
    const lowIndex = actualVisible.reduce((best, index) => Number(this.bundle.candles[index].low) < Number(this.bundle.candles[best].low) ? index : best, actualVisible[0]);
    const highValue = Number(this.bundle.candles[highIndex].high);
    const lowValue = Number(this.bundle.candles[lowIndex].low);
    const highX = this.xFromIndex(highIndex);
    const lowX = this.xFromIndex(lowIndex);
    const highY = yPrice(highValue);
    const lowY = yPrice(lowValue);
    const highLabelY = Math.max(top + 20, highY - 28);
    const lowLabelY = Math.min(priceBottom - 14, lowY + 28);

    ctx.save();
    ctx.strokeStyle = "#4d545c";
    ctx.beginPath();
    ctx.moveTo(highX, highY - 2);
    ctx.lineTo(highX, Math.max(top + 8, highLabelY - 8));
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(highX - 4, Math.max(top + 12, highLabelY - 14));
    ctx.lineTo(highX, Math.max(top + 8, highLabelY - 8));
    ctx.lineTo(highX + 4, Math.max(top + 12, highLabelY - 14));
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(lowX, lowY + 2);
    ctx.lineTo(lowX, Math.min(priceBottom - 8, lowLabelY - 8));
    ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(lowX - 4, Math.min(priceBottom - 12, lowLabelY - 14));
    ctx.lineTo(lowX, Math.min(priceBottom - 8, lowLabelY - 8));
    ctx.lineTo(lowX + 4, Math.min(priceBottom - 12, lowLabelY - 14));
    ctx.stroke();
    ctx.restore();
    this.drawTextBox(ctx, highX, highLabelY, `High  ${formatPrice(highValue)}`, {
      anchor: "center",
      fill: COLORS.text,
      bg: "#ffffff",
      outline: "#d7dbde",
      font: "bold 10px Helvetica",
    });
    this.drawTextBox(ctx, lowX, lowLabelY, `Low  ${formatPrice(lowValue)}`, {
      anchor: "center",
      fill: COLORS.text,
      bg: "#ffffff",
      outline: "#d7dbde",
      font: "bold 10px Helvetica",
    });

    if (this.paneIndicators().length) {
      this.drawIndicatorPanes(ctx, visible, left, right, indicatorTop, bottom, bodyWidth, width);
      ctx.save();
      ctx.strokeStyle = this.resizingDivider ? "#738271" : "#a8b7a2";
      ctx.lineWidth = this.resizingDivider ? 2 : 1;
      ctx.beginPath();
      ctx.moveTo(0, indicatorTop + 0.5);
      ctx.lineTo(width, indicatorTop + 0.5);
      ctx.stroke();
      ctx.restore();
    }

    ctx.save();
    ctx.fillStyle = COLORS.text;
    ctx.font = "10px Helvetica";
    ctx.textAlign = "center";
    for (let step = 0; step < 6; step += 1) {
      const relative = step / 5;
      const rawIndex = this.viewLeft + relative * this.viewCount;
      const labelIndex = Math.max(0, Math.min(this.bundle.candles.length - 1, Math.round(rawIndex)));
      const x = this.xFromIndex(rawIndex);
      const date = new Date(this.bundle.candles[labelIndex].open_time);
      const label = date.toISOString().slice(11, 16);
      ctx.fillText(label, x, bottom - 6);
    }
    ctx.restore();

    if (this.hoverX !== null && this.hoverY !== null) {
      const hoverPrice = priceFromY(this.hoverY);
      const hoverCandle = this.hoverIndex === null ? null : this.bundle.candles[this.hoverIndex];
      ctx.save();
      ctx.strokeStyle = "#6a737d";
      ctx.lineWidth = 1.35;
      ctx.setLineDash([3, 4]);
      ctx.beginPath();
      ctx.moveTo(this.hoverX, top);
      ctx.lineTo(this.hoverX, priceBottom);
      ctx.stroke();
      ctx.beginPath();
      ctx.moveTo(left, this.hoverY);
      ctx.lineTo(right, this.hoverY);
      ctx.stroke();
      ctx.restore();

      this.drawTextBox(ctx, right + 6, this.hoverY, formatPrice(hoverPrice), {
        anchor: "w",
        fill: "#ffffff",
        bg: "#2a3138",
        outline: "#3c454e",
        font: "bold 10px Helvetica",
        padX: 8,
        padY: 4,
      });

      if (hoverCandle) {
        const timeLabelY = Math.max(priceBottom + 16, bottom - 12);
        this.drawTextBox(ctx, this.hoverX, timeLabelY, formatCrosshairTime(hoverCandle.open_time), {
          anchor: "center",
          fill: "#ffffff",
          bg: "#20252b",
          outline: "#303841",
          font: "10px Helvetica",
          padX: 8,
          padY: 4,
        });
      }
    }
  }
}

const chart = new TradingWebChart(elements.chartCanvas, {
  onHover: (index) => {
    state.hoverIndex = index;
    renderHeader();
    renderBottomMeta();
  },
  onLeave: () => {
    state.hoverIndex = null;
    renderHeader();
    renderBottomMeta();
  },
});

function currentBundle() {
  return state.payload?.bundles?.[state.selectedSymbol] ?? null;
}

function setStatus(text) {
  elements.statusText.textContent = text;
}

function renderTimeframeButtons() {
  elements.timeframeButtons.innerHTML = "";
  (state.payload?.intervals ?? []).forEach((interval) => {
    const button = document.createElement("button");
    button.className = `control-button ${state.selectedInterval === interval ? "active" : ""}`;
    button.textContent = formatIntervalLabel(interval);
    button.addEventListener("click", () => {
      if (state.selectedInterval === interval) {
        return;
      }
      state.selectedInterval = interval;
      renderTimeframeButtons();
      refreshData();
    });
    elements.timeframeButtons.appendChild(button);
  });
}

function renderModeButtons() {
  elements.modeButtons.innerHTML = "";
  [
    ["candles", "Candles"],
    ["footprint", "Footprint"],
  ].forEach(([mode, label]) => {
    const button = document.createElement("button");
    button.className = `control-button ${state.chartMode === mode ? "active" : ""}`;
    button.textContent = label;
    button.addEventListener("click", () => {
      state.chartMode = mode;
      chart.setDisplayMode(mode);
      renderModeButtons();
    });
    elements.modeButtons.appendChild(button);
  });
}

function renderIndicatorPopup() {
  const popup = elements.indicatorPopup;
  popup.innerHTML = "";
  const title = document.createElement("div");
  title.className = "indicator-popup__title";
  title.textContent = "Indicators";
  popup.appendChild(title);
  (state.payload?.indicator_options ?? []).forEach((option) => {
    const row = document.createElement("div");
    row.className = `indicator-option ${state.selectedIndicators.includes(option.key) ? "active" : ""}`;
    row.textContent = option.label;
    row.addEventListener("click", (event) => {
      event.stopPropagation();
      if (state.selectedIndicators.includes(option.key)) {
        state.selectedIndicators = state.selectedIndicators.filter((item) => item !== option.key);
      } else {
        state.selectedIndicators = [...state.selectedIndicators, option.key];
      }
      chart.setSelectedIndicators(state.selectedIndicators);
      renderIndicatorPopup();
      renderIndicatorsButton();
      renderBottomMeta();
    });
    popup.appendChild(row);
  });
}

function renderIndicatorsButton() {
  const open = !elements.indicatorPopup.classList.contains("hidden");
  elements.indicatorsButton.classList.toggle("active", open || state.selectedIndicators.length > 0);
}

function renderWatchlist() {
  elements.watchlistRows.innerHTML = "";
  (state.payload?.watchlist ?? []).forEach((rowData) => {
    const row = document.createElement("button");
    row.className = `watch-row ${rowData.symbol === state.selectedSymbol ? "active" : ""}`;
    row.type = "button";
    const badge = badgeForSymbol(rowData.symbol);
    row.innerHTML = `
      <span class="watch-row__symbol">
        <span class="watch-row__badge" style="background:${badge.bg}; color:${badge.fg};">${badge.text}</span>
        <span>
          <span class="watch-row__primary">${rowData.display_symbol}</span><br />
          <span class="watch-row__secondary">${rowData.setup_name}</span>
        </span>
      </span>
      <span class="watch-row__value">${formatPrice(rowData.last)}</span>
      <span class="watch-row__value ${rowData.change >= 0 ? "positive" : "negative"}">${formatChange(rowData.change, rowData.percent).value}</span>
      <span class="watch-row__value ${rowData.change >= 0 ? "positive" : "negative"}">${formatChange(rowData.change, rowData.percent).percent}</span>
    `;
    row.addEventListener("click", () => {
      state.selectedSymbol = rowData.symbol;
      state.hoverIndex = null;
      renderAll();
    });
    elements.watchlistRows.appendChild(row);
  });
}

function renderSetup() {
  const bundle = currentBundle();
  if (!bundle) return;
  const signal = bundle.analysis.signal;
  const response = bundle.analysis.response;
  const rows = [
    { label: "Breakdown retest", value: signal?.setup_name ?? "No active setup", color: signal ? "#f23645" : "#7f8792" },
    { label: "Sell strength", value: Number(bundle.analysis.trade_flow.sell_strength).toFixed(2), color: "#f23645" },
    { label: "Blocked buying", value: Number(response.blocked_buying_score).toFixed(2), color: "#ff9800" },
    { label: "Book imbalance", value: Number(bundle.analysis.book_imbalance).toFixed(2), color: Number(bundle.analysis.book_imbalance) >= 0 ? "#22ab94" : "#f23645" },
    { label: "Invalidation above", value: signal ? signal.invalidation_level : "—", color: "#7f8792" },
  ];
  elements.setupRows.innerHTML = "";
  rows.forEach((row) => {
    const node = document.createElement("div");
    node.className = "setup-row";
    node.innerHTML = `
      <span class="setup-row__label">${row.label}</span>
      <span class="setup-row__value" style="color:${row.color}">${row.value}</span>
    `;
    elements.setupRows.appendChild(node);
  });
  elements.setupNote.textContent = signal?.notes ?? "No structured bearish setup is active right now. The assistant is still monitoring price, flow, and book response.";
}

function renderHeader() {
  const bundle = currentBundle();
  if (!bundle) return;
  const summary = latestSummary(bundle, state.hoverIndex);
  const timestamp = state.hoverIndex === null
    ? "Kraken public"
    : new Date(bundle.candles[state.hoverIndex].open_time).toISOString().replace("T", " ").slice(0, 16) + " UTC";

  elements.symbolChipLabel.textContent = state.selectedSymbol.replace("/", "");
  elements.chartTitle.textContent = displayMarketName(state.selectedSymbol);
  elements.chartContext.textContent = `${bundle.interval_label}  ${timestamp}`;
  elements.openValue.textContent = `Open ${formatPrice(summary.open)}`;
  elements.highValue.textContent = `High ${formatPrice(summary.high)}`;
  elements.lowValue.textContent = `Low ${formatPrice(summary.low)}`;
  elements.closeValue.textContent = `Close ${formatPrice(summary.close)}`;
  elements.closeValue.style.color = summary.priceChange >= 0 ? COLORS.priceUp : COLORS.priceDown;
  elements.changeValue.textContent = formatChange(summary.priceChange, summary.percentChange).percent;
  elements.changeValue.style.color = summary.priceChange >= 0 ? COLORS.priceUp : COLORS.priceDown;
  elements.ema12.textContent = `EMA 12 ${formatPrice(summary.ema12)}`;
  elements.ema144.textContent = `EMA 144 ${formatPrice(summary.ema144)}`;
  elements.ema169.textContent = `EMA 169 ${formatPrice(summary.ema169)}`;
  elements.ema238.textContent = `EMA 238 ${formatPrice(summary.ema238)}`;
  elements.ema338.textContent = `EMA 338 ${formatPrice(summary.ema338)}`;
}

function renderBottomMeta() {
  const bundle = currentBundle();
  if (!bundle) {
    elements.bottomMeta.textContent = "Waiting for first refresh…";
    return;
  }
  const paneIndicatorCount = state.selectedIndicators.filter((indicator) => PANE_INDICATORS.has(indicator)).length;
  const resizeHint = paneIndicatorCount ? " · Drag divider to resize panes" : "";
  if (state.hoverIndex === null) {
    elements.bottomMeta.textContent = `Drag chart to pan · Scroll to zoom${resizeHint} · ${bundle.interval_label} · Last update successful`;
    return;
  }
  const timestamp = new Date(bundle.candles[state.hoverIndex].open_time).toISOString().replace("T", " ").slice(0, 16) + " UTC";
  elements.bottomMeta.textContent = `Viewing ${timestamp} · Drag to pan · Scroll to zoom${resizeHint}`;
}

function renderAll() {
  if (!state.payload) return;
  const bundle = currentBundle();
  if (bundle) {
    chart.setBundle(bundle);
    chart.setDisplayMode(state.chartMode);
    chart.setSelectedIndicators(state.selectedIndicators);
  }
  renderTimeframeButtons();
  renderModeButtons();
  renderIndicatorsButton();
  renderIndicatorPopup();
  renderWatchlist();
  renderSetup();
  renderHeader();
  renderBottomMeta();
  setStatus(`Kraken public · ${formatIntervalLabel(state.selectedInterval)} updated`);
}

function applyPayload(payload) {
  state.payload = payload;
  state.hoverIndex = null;
  if (!state.payload.bundles[state.selectedSymbol]) {
    state.selectedSymbol = state.payload.selected_symbol;
  }
  renderAll();
}

async function requestIntervalPayload(interval, symbol) {
  const existing = state.inflightPayloads.get(interval);
  if (existing) {
    return existing;
  }
  const params = new URLSearchParams({
    symbol,
    interval: String(interval),
  });
  const request = (async () => {
    const response = await fetch(`/api/dashboard?${params.toString()}`);
    if (!response.ok) {
      throw new Error(`Dashboard request failed with ${response.status}`);
    }
    const payload = await response.json();
    state.payloadCache.set(interval, { timestamp: Date.now(), payload });
    return payload;
  })();
  state.inflightPayloads.set(interval, request);
  try {
    return await request;
  } finally {
    state.inflightPayloads.delete(interval);
  }
}

async function refreshData() {
  const cacheKey = state.selectedInterval;
  const cached = state.payloadCache.get(cacheKey);
  const cacheAge = cached ? Date.now() - cached.timestamp : Number.POSITIVE_INFINITY;
  const hasFreshCache = Boolean(cached) && cacheAge < CLIENT_CACHE_TTL_MS;

  if (hasFreshCache) {
    applyPayload(cached.payload);
    warmIntervalCache();
    return;
  }

  if (cached) {
    applyPayload(cached.payload);
    setStatus(`Refreshing Kraken ${formatIntervalLabel(state.selectedInterval)} snapshot…`);
  } else {
    setStatus(`Refreshing Kraken ${formatIntervalLabel(state.selectedInterval)} snapshot…`);
  }

  try {
    const payload = await requestIntervalPayload(state.selectedInterval, state.selectedSymbol);
    if (state.selectedInterval === cacheKey) {
      applyPayload(payload);
    }
    warmIntervalCache();
  } catch (error) {
    setStatus("Refresh failed");
    throw error;
  }
}

async function warmInterval(interval) {
  if (interval === state.selectedInterval || state.warmingIntervals.has(interval)) {
    return;
  }
  const cached = state.payloadCache.get(interval);
  if (cached && Date.now() - cached.timestamp < CLIENT_CACHE_TTL_MS) {
    return;
  }
  state.warmingIntervals.add(interval);
  try {
    await requestIntervalPayload(interval, state.selectedSymbol);
  } catch (_error) {
    // Warm-cache failures should stay silent; active refresh still reports errors.
  } finally {
    state.warmingIntervals.delete(interval);
  }
}

function warmIntervalCache() {
  const intervals = (state.payload?.intervals ?? []).filter((interval) => interval !== state.selectedInterval);
  intervals.forEach((interval, index) => {
    window.setTimeout(() => {
      warmInterval(interval);
    }, 40 + index * 60);
  });
}

function scheduleAutoRefresh() {
  if (state.autoTimer) clearInterval(state.autoTimer);
  state.autoTimer = null;
  if (!state.autoRefresh) return;
  state.autoTimer = window.setInterval(() => refreshData().catch((error) => console.error(error)), 60_000);
}

function bindControls() {
  elements.refreshButton.addEventListener("click", () => refreshData().catch((error) => console.error(error)));
  elements.autoButton.addEventListener("click", () => {
    state.autoRefresh = !state.autoRefresh;
    elements.autoButton.textContent = state.autoRefresh ? "Auto: On" : "Auto: Off";
    elements.autoButton.classList.toggle("active", state.autoRefresh);
    scheduleAutoRefresh();
  });
  elements.indicatorsButton.addEventListener("click", (event) => {
    event.stopPropagation();
    elements.indicatorPopup.classList.toggle("hidden");
    renderIndicatorsButton();
  });
  document.addEventListener("click", (event) => {
    if (!elements.indicatorPopup.contains(event.target) && event.target !== elements.indicatorsButton) {
      elements.indicatorPopup.classList.add("hidden");
      renderIndicatorsButton();
    }
  });
}

bindControls();
refreshData().catch((error) => {
  console.error(error);
  setStatus(`Refresh failed: ${error.message}`);
});
