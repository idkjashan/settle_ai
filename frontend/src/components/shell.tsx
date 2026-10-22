"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon, type IconName } from "./icons";
import { useTheme, useToast } from "./providers";
import { useClaims } from "@/lib/store";

interface NavEntry {
  href: string;
  label: string;
  shortLabel: string;
  icon: IconName;
  active: (path: string) => boolean;
}

const NAV: NavEntry[] = [
  { href: "/", label: "Overview", shortLabel: "Home", icon: "grid", active: (p) => p === "/" },
  { href: "/claims", label: "Claims", shortLabel: "Claims", icon: "file", active: (p) => p.startsWith("/claims") },
  { href: "/new-claim", label: "New claim", shortLabel: "New", icon: "plus", active: (p) => p.startsWith("/new-claim") },
  { href: "/guardrails", label: "Guardrails", shortLabel: "Rules", icon: "shield", active: (p) => p.startsWith("/guardrails") },
  { href: "/audit", label: "Audit trail", shortLabel: "Audit", icon: "history", active: (p) => p.startsWith("/audit") },
];

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <Link className={`brand ${compact ? "brand-compact" : ""}`} href="/">
      <span className="brand-mark" aria-hidden="true">
        <span />
        <span />
        <span />
      </span>
      <span className="brand-copy">
        <strong>auto-settle</strong>
        {!compact && <small>CLAIMS DESK</small>}
      </span>
    </Link>
  );
}

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { theme, toggleTheme } = useTheme();
  const showToast = useToast();
  const { claims, apiOnline, refreshAll, resetDemoState } = useClaims();
  const [search, setSearch] = useState("");

  useEffect(() => {
    setSearch("");
  }, [pathname]);

  const apiClass = apiOnline == null ? "" : apiOnline ? "online" : "offline";
  const apiText = apiOnline == null ? "CONNECTING…" : apiOnline ? "LIVE API ACTIVE" : "API OFFLINE";

  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary navigation">
        <Brand />
        <div className="workspace-switch">
          <span className="workspace-dot" />
          <span>Northstar Assurance</span>
          <span className="chevron">⌄</span>
        </div>
        <p className="nav-label">WORKSPACE</p>
        <nav className="primary-nav">
          {NAV.slice(0, 3).map((e) => (
            <Link key={e.href} href={e.href} className={`nav-item ${e.active(pathname) ? "is-active" : ""}`}>
              <Icon name={e.icon} />
              <span>{e.label}</span>
              {e.href === "/claims" && claims.length > 0 && <span className="nav-count">{claims.length}</span>}
            </Link>
          ))}
        </nav>
        <p className="nav-label nav-label-spaced">REVIEW</p>
        <nav className="primary-nav">
          {NAV.slice(3).map((e) => (
            <Link key={e.href} href={e.href} className={`nav-item ${e.active(pathname) ? "is-active" : ""}`}>
              <Icon name={e.icon} />
              <span>{e.label}</span>
            </Link>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="prototype-note">
            <span className={`live-dot ${apiClass}`} />
            <span>
              <strong>Production Claims Desk</strong>
              <small>Autonomously bounded adjudication</small>
            </span>
          </div>
          <button className="profile-button" type="button" aria-label="Signed in as Nisha Rao">
            <span className="avatar">NR</span>
            <span className="profile-copy">
              <strong>Nisha Rao</strong>
              <small>Claims adjuster</small>
            </span>
            <span className="more">···</span>
          </button>
        </div>
      </aside>

      <div className="main-area">
        <div className="mobile-topbar">
          <Brand compact />
          <span className="mobile-claim-pill">
            <span className={`live-dot ${apiClass}`} /> Live Desk
          </span>
        </div>

        <main className="main-content">
          <header className="topbar">
            <div className="crumbs">
              <span>Claims desk</span>
              <span className="crumb-slash">/</span>
              <span id="topbar-context"><Breadcrumbs pathname={pathname} /></span>
            </div>
            <div className="topbar-actions">
              <span className="demo-pill">
                <span className={`live-dot ${apiClass}`} /> {apiText}
              </span>
              <div className="search-wrap">
                <span className="search-icon-pos">
                  <Icon name="search" />
                </span>
                <input
                  type="text"
                  className="search-input"
                  placeholder="Search claims..."
                  aria-label="Search claims"
                  value={search}
                  onChange={(e) => {
                    setSearch(e.target.value);
                    router.push(e.target.value.trim() ? `/claims?q=${encodeURIComponent(e.target.value)}` : "/claims");
                  }}
                />
              </div>
              <button
                className="icon-button"
                type="button"
                aria-label="Sync with backend"
                title="Sync with backend"
                onClick={() => {
                  void refreshAll();
                  showToast("Synced with backend — claims refreshed.");
                }}
              >
                <Icon name="clock" />
              </button>
              <button
                className="icon-button"
                type="button"
                aria-label="Reset jury demo"
                title="Reset jury demo (purges rehearsal claims & locks)"
                onClick={async () => {
                  if (window.confirm("Reset demo environment? This purges test rehearsal claims and resets locks.")) {
                    try {
                      await resetDemoState();
                      showToast("Jury demo reset: rehearsal claims purged & locks cleared.");
                    } catch {
                      showToast("Demo reset failed — backend may be offline.");
                    }
                  }
                }}
              >
                <Icon name="history" />
              </button>
              <button className="icon-button" type="button" onClick={toggleTheme} aria-label="Toggle dark/light theme" title="Toggle theme">
                <Icon name={theme === "dark" ? "sun" : "moon"} />
              </button>
              <button
                className="icon-button"
                type="button"
                aria-label="Help"
                onClick={() => showToast("Auto-Settle AI: Autonomous video-to-cash claims adjuster. Stage 0 to Stage 6 active.")}
              >
                <Icon name="help" />
              </button>
              <span className="avatar avatar-small">NR</span>
            </div>
          </header>
          {children}
          <footer className="app-footer">
            <span>
              Auto-Settle AI <i>·</i> Autonomous Motor Claims Desk
            </span>
            <span>Built around clear mathematical boundaries, not guesswork.</span>
          </footer>
        </main>
      </div>

      <nav className="mobile-nav" aria-label="Mobile navigation">
        {NAV.map((e) => (
          <Link key={e.href} href={e.href} className={`mobile-nav-item ${e.active(pathname) ? "is-active" : ""} ${e.href === "/new-claim" ? "mobile-new" : ""}`}>
            <Icon name={e.icon} />
            <small>{e.shortLabel}</small>
          </Link>
        ))}
      </nav>
    </div>
  );
}

function Breadcrumbs({ pathname }: { pathname: string }) {
  if (pathname === "/") return <span>Overview</span>;
  if (pathname.startsWith("/claims/")) return <span>Claim review</span>;
  if (pathname.startsWith("/claims")) return <span>Claims</span>;
  if (pathname.startsWith("/new-claim")) return <span>New claim</span>;
  if (pathname.startsWith("/guardrails")) return <span>Guardrails</span>;
  if (pathname.startsWith("/audit")) return <span>Audit trail</span>;
  return <span>Overview</span>;
}
