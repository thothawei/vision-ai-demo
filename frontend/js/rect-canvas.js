// M10/M11 共用：拖曳畫矩形 ROI 的 canvas 控制器。
// mode 無 tag：每次拖曳都新增一個矩形（M10 多個 ROI）。
// 有 tag（例如 "ref"/"measure"）：同一個 tag 重畫會取代舊的（M11 標準色區/量測區各只有一個）。
export function createRectCanvasController(canvas) {
  const ctx = canvas.getContext("2d");
  let img = null;
  let items = []; // [{tag: string|null, rect: [x1,y1,x2,y2]}]
  let currentTag = null;
  let dragging = null;
  const COLOR_SEQ = ["#0071e3", "#34c759", "#ff9500", "#ff3b30", "#af52de", "#5ac8fa"];
  const TAG_COLORS = { ref: "#ff9500", measure: "#0071e3" };

  function colorFor(item, idx) {
    if (item.tag && TAG_COLORS[item.tag]) return TAG_COLORS[item.tag];
    return COLOR_SEQ[idx % COLOR_SEQ.length];
  }

  function redraw(previewRect) {
    if (!img) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    items.forEach((item, idx) => {
      const [x1, y1, x2, y2] = item.rect;
      ctx.strokeStyle = colorFor(item, idx);
      ctx.lineWidth = 2;
      ctx.strokeRect(x1 * canvas.width, y1 * canvas.height, (x2 - x1) * canvas.width, (y2 - y1) * canvas.height);
      ctx.fillStyle = ctx.strokeStyle;
      ctx.font = "13px sans-serif";
      const label = item.tag ? (item.tag === "ref" ? "標準" : "量測") : String(idx + 1);
      ctx.fillText(label, x1 * canvas.width + 4, y1 * canvas.height + 14);
    });
    if (previewRect) {
      const [x1, y1, x2, y2] = previewRect;
      ctx.strokeStyle = "#8e8e93";
      ctx.setLineDash([4, 4]);
      ctx.strokeRect(x1 * canvas.width, y1 * canvas.height, (x2 - x1) * canvas.width, (y2 - y1) * canvas.height);
      ctx.setLineDash([]);
    }
  }

  function loadFile(file) {
    return new Promise((resolve) => {
      const image = new Image();
      image.onload = () => {
        img = image;
        const maxW = 860;
        const scale = Math.min(1, maxW / img.width);
        canvas.width = img.width * scale;
        canvas.height = img.height * scale;
        canvas.style.display = "block";
        items = [];
        redraw();
        resolve();
      };
      image.src = URL.createObjectURL(file);
    });
  }

  canvas.addEventListener("mousedown", (e) => {
    if (!img) return;
    const r = canvas.getBoundingClientRect();
    dragging = { x1: (e.clientX - r.left) / r.width, y1: (e.clientY - r.top) / r.height };
  });
  canvas.addEventListener("mousemove", (e) => {
    if (!dragging || !img) return;
    const r = canvas.getBoundingClientRect();
    const x2 = (e.clientX - r.left) / r.width, y2 = (e.clientY - r.top) / r.height;
    redraw([Math.min(dragging.x1, x2), Math.min(dragging.y1, y2), Math.max(dragging.x1, x2), Math.max(dragging.y1, y2)]);
  });
  canvas.addEventListener("mouseup", (e) => {
    if (!dragging || !img) return;
    const r = canvas.getBoundingClientRect();
    const x2 = (e.clientX - r.left) / r.width, y2 = (e.clientY - r.top) / r.height;
    const x1 = Math.min(dragging.x1, x2), y1 = Math.min(dragging.y1, y2);
    const xx2 = Math.max(dragging.x1, x2), yy2 = Math.max(dragging.y1, y2);
    dragging = null;
    if (xx2 - x1 > 0.01 && yy2 - y1 > 0.01) {
      if (currentTag) items = items.filter((it) => it.tag !== currentTag);
      items.push({ tag: currentTag, rect: [x1, y1, xx2, yy2] });
    }
    redraw();
  });

  return {
    loadFile,
    setTag: (tag) => { currentTag = tag; },
    getRect: (tag) => { const it = items.find((i) => i.tag === tag); return it ? it.rect : null; },
    getAllRects: () => items.map((i) => i.rect),
    removeLast: () => { items.pop(); redraw(); },
    clear: () => { items = []; redraw(); },
    hasImage: () => img !== null,
  };
}

