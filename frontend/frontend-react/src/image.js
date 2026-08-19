export async function convertImageToPng(file) {
  if (!file?.type?.startsWith("image/")) throw new Error("이미지 파일만 사용할 수 있어요.");

  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const canvas = document.createElement("canvas");
  canvas.width = bitmap.width;
  canvas.height = bitmap.height;
  const context = canvas.getContext("2d");
  if (!context) {
    bitmap.close();
    throw new Error("이미지를 변환할 수 없어요.");
  }

  context.drawImage(bitmap, 0, 0);
  bitmap.close();
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((result) => result ? resolve(result) : reject(new Error("PNG 변환에 실패했어요.")), "image/png");
  });
  const baseName = file.name?.replace(/\.[^.]+$/, "") || "document";
  return new File([blob], `${baseName}.png`, { type: "image/png", lastModified: Date.now() });
}

export async function captureVideoFrameAsPng(video, filename = "camera-capture.png") {
  if (!video?.videoWidth || !video?.videoHeight) throw new Error("카메라 화면을 준비하는 중이에요.");
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const context = canvas.getContext("2d");
  if (!context) throw new Error("카메라 이미지를 만들 수 없어요.");
  context.drawImage(video, 0, 0);
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((result) => result ? resolve(result) : reject(new Error("PNG 변환에 실패했어요.")), "image/png");
  });
  return new File([blob], filename, { type: "image/png", lastModified: Date.now() });
}
