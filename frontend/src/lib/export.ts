const SCALE = 3; // enough resolution that the 8pt form captions stay legible

/**
 * Rasterise an inline SVG. The sheet uses system-safe font stacks so the
 * serialised markup renders without embedding any font data.
 */
async function svgToCanvas(svg: SVGSVGElement, scale = SCALE): Promise<HTMLCanvasElement> {
  const viewBox = svg.viewBox.baseVal;
  const width = viewBox.width || svg.clientWidth;
  const height = viewBox.height || svg.clientHeight;

  const clone = svg.cloneNode(true) as SVGSVGElement;
  clone.setAttribute("width", String(width));
  clone.setAttribute("height", String(height));
  clone.setAttribute("xmlns", "http://www.w3.org/2000/svg");

  // Resolve the CSS custom properties the sheet uses; a detached SVG has no
  // cascade to read them from.
  const computed = getComputedStyle(document.documentElement);
  const paper = computed.getPropertyValue("--color-paper").trim() || "#f4efe3";
  const shade = computed.getPropertyValue("--color-paper-shade").trim() || "#e2dac9";
  let markup = new XMLSerializer().serializeToString(clone);
  markup = markup
    .replace(/var\(--color-paper-shade\)/g, shade)
    .replace(/var\(--color-paper\)/g, paper);

  const blob = new Blob([markup], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);

  try {
    const image = await new Promise<HTMLImageElement>((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("Could not rasterise the log sheet"));
      img.src = url;
    });

    const canvas = document.createElement("canvas");
    canvas.width = Math.round(width * scale);
    canvas.height = Math.round(height * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Canvas is unavailable in this browser");
    ctx.fillStyle = paper;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    return canvas;
  } finally {
    URL.revokeObjectURL(url);
  }
}

function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function downloadSheetPng(svg: SVGSVGElement, filename: string): Promise<void> {
  const canvas = await svgToCanvas(svg);
  const blob = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, "image/png"));
  if (!blob) throw new Error("Could not create the PNG");
  saveBlob(blob, filename);
}

/** One landscape page per daily log sheet. */
export async function downloadLogsPdf(svgs: SVGSVGElement[], filename: string): Promise<void> {
  if (!svgs.length) return;

  // Loaded on demand: jsPDF is large and most visits never export.
  const { jsPDF } = await import("jspdf");
  const pdf = new jsPDF({ orientation: "landscape", unit: "pt", format: "letter" });
  const pageW = pdf.internal.pageSize.getWidth();
  const pageH = pdf.internal.pageSize.getHeight();
  const margin = 22;

  for (let i = 0; i < svgs.length; i += 1) {
    if (i > 0) pdf.addPage();
    const canvas = await svgToCanvas(svgs[i]);
    const ratio = canvas.height / canvas.width;
    const width = pageW - margin * 2;
    const height = Math.min(width * ratio, pageH - margin * 2);
    pdf.addImage(
      canvas.toDataURL("image/png"),
      "PNG",
      margin,
      (pageH - height) / 2,
      width,
      height,
      undefined,
      "FAST",
    );
  }

  pdf.save(filename);
}
