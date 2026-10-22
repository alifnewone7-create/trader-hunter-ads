import { Download } from "lucide-react";

const URL = `${process.env.REACT_APP_BACKEND_URL}/api/download/source`;

export default function DownloadPage() {
  return (
    <div className="landing flex min-h-screen items-center justify-center bg-[#0B0F19] px-5" data-testid="download-page">
      <div className="glow glow-a" aria-hidden />
      <div className="reveal relative w-full max-w-sm text-center">
        <h1 className="text-2xl font-bold text-white" data-testid="download-title">সোর্স কোড ডাউনলোড</h1>
        <p className="mt-2 text-sm text-slate-400">পুরো ওয়েবসাইটের সোর্স কোড ZIP ফাইল হিসেবে ডাউনলোড হবে।</p>
        <a
          href={URL}
          download
          data-testid="download-source-button"
          className="cta-btn mt-8 flex w-full items-center justify-center gap-3 rounded-2xl py-4 text-lg font-bold text-white"
        >
          <Download className="h-6 w-6" /> ZIP ডাউনলোড করুন
        </a>
      </div>
    </div>
  );
}
