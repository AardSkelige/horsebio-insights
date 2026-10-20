const SLOT_PATH = /^\/raw-materials\/slot\/([^/]+)\/?$/;

export default function slotFromCode(text) {
    try {
        const match = new URL(text).pathname.match(SLOT_PATH);
        return match ? decodeURIComponent(match[1]) : null;
    } catch {
        return null;
    }
}
