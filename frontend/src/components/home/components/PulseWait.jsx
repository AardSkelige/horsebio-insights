export default function PulseWait() {
    return (
        <div className="home-pulse home-pulse--wait" aria-hidden="true">
            <svg className="home-pulse__ghost" viewBox="0 0 100 100" preserveAspectRatio="none">
                <path d="M0 72 C8 70 12 52 20 56 S32 78 42 64 S56 30 66 42 S82 66 90 40 S97 26 100 30" />
            </svg>
        </div>
    );
}
