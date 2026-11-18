/**
 * Tạo âm thanh cảnh báo bằng Web Audio API (không cần tải file MP3 ngoài).
 * - playSuccessBeep(): 2 nốt nhẹ khi thực phẩm đạt chuẩn hoặc lưu phiếu thành công.
 * - playRejectAlarm(): âm báo khẩn khi phát hiện thực phẩm hư hỏng (REJECTED).
 */
let audioCtx = null;

function getCtx() {
  if (!audioCtx) {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (AudioContext) audioCtx = new AudioContext();
  }
  if (audioCtx && audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  return audioCtx;
}

function tone(freq, durationMs, delayMs = 0, type = "sine", gainVal = 0.12) {
  const ctx = getCtx();
  if (!ctx) return;
  const start = ctx.currentTime + delayMs / 1000;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  gain.gain.setValueAtTime(gainVal, start);
  gain.gain.exponentialRampToValueAtTime(0.001, start + durationMs / 1000);
  osc.connect(gain);
  gain.connect(ctx.destination);
  osc.start(start);
  osc.stop(start + durationMs / 1000);
}

export function playSuccessBeep() {
  tone(880, 110, 0, "sine", 0.1);
  tone(1174, 150, 120, "sine", 0.1);
}

export function playRejectAlarm() {
  tone(420, 180, 0, "sawtooth", 0.14);
  tone(330, 220, 200, "sawtooth", 0.14);
  tone(420, 220, 440, "sawtooth", 0.14);
}
