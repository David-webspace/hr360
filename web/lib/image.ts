// 上傳前先在瀏覽器縮到長邊 1600px 並轉成 JPEG：省頻寬與模型 token，重新繪製也順便丟掉 EXIF（含拍攝地點）
export async function shrinkImage(file: File, maxSide = 1600): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  return new Promise((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("無法處理這張圖片"))), "image/jpeg", 0.85),
  );
}
