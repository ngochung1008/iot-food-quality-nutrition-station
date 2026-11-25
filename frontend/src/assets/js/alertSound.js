/**
 * Tạo âm thanh cảnh báo bằng Web Audio API (không cần tải file MP3 ngoài).
 * - playSuccessBeep(): 1 tiếng bíp nhẹ khi cộng dồn / tích xanh thành công.
 * - playRejectAlarm(): 2 tiếng bíp trầm khi phát hiện thực phẩm hư hỏng (REJECTED).
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
  tone(980, 115, 0, "sine", 0.11);
}

export function playRejectAlarm() {
  tone(300, 170, 0, "sawtooth", 0.14);
  tone(260, 210, 210, "sawtooth", 0.14);
}
