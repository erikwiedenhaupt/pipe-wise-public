// pages/_app.js
import "../styles/globals.css";

export default function App({ Component, pageProps }) {
  return (
    <div className="min-h-screen bg-[var(--bg)] text-slate-100">
      <Component {...pageProps} />
    </div>
  );
}