const fallbackRandomUUID = () => {
  const bytes = new Uint8Array(16);
  if (globalThis.crypto?.getRandomValues) {
    globalThis.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i++) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
};

if (typeof globalThis.crypto?.randomUUID !== 'function') {
  // Direct assignment works when Object.defineProperty fails on non-configurable prototype getter
  try { globalThis.crypto.randomUUID = fallbackRandomUUID; } catch (_) {}

  // If still not patched, replace the crypto object entirely
  if (typeof globalThis.crypto?.randomUUID !== 'function') {
    const orig = globalThis.crypto;
    try {
      Object.defineProperty(globalThis, 'crypto', {
        configurable: true,
        get: () => ({
          randomUUID: fallbackRandomUUID,
          getRandomValues: orig?.getRandomValues?.bind(orig),
          subtle: orig?.subtle,
        }),
      });
    } catch (_) {}
  }
}
