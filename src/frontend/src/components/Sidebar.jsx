import { useLocation, useNavigate } from "react-router-dom";
import { useSidebar } from "../context/SidebarContext";
import {
  LayoutDashboard, TrendingUp, ShoppingBasket, ChevronRight, Home,
} from "lucide-react";

const navItems = [
  { id: "/",      icon: Home,            label: "Beranda" },
  { id: "/app",   icon: LayoutDashboard, label: "Dashboard" },
  { id: "/tren",  icon: TrendingUp,      label: "Market Trends" },
];

export default function Sidebar() {
  const location  = useLocation();
  const navigate  = useNavigate();
  const { collapsed, toggle } = useSidebar();

  return (
    <aside style={{
      ...styles.sidebar,
      width: collapsed ? 64 : 230,
    }}>

      {/* Logo — klik untuk toggle */}
      <div
        onClick={toggle}
        title={collapsed ? "Buka sidebar" : "Sembunyikan sidebar"}
        style={{
          ...styles.logoRow,
          justifyContent: collapsed ? "center" : "flex-start",
          marginBottom: 28,
        }}
      >
        <div style={styles.logoIcon}>
          <img src="/logo-white.svg" style={{ width:42, height:42 }} alt="MarketCast" />
        </div>
        {!collapsed && (
          <div style={{ overflow: "hidden" }}>
            <div style={styles.logoText}>MarketCast</div>
            <div style={styles.logoSub}>Kota Surabaya</div>
          </div>
        )}
      </div>

      {/* Nav label */}
      {!collapsed && (
        <p style={styles.navLabel}>MENU</p>
      )}

      {/* Nav items */}
      {navItems.map(({ id, icon: Icon, label }) => {
        const active = location.pathname === id;
        return (
          <div
            key={id}
            onClick={() => navigate(id)}
            title={collapsed ? label : ""}
            style={{
              ...styles.navItem,
              ...(active ? styles.navActive : {}),
              justifyContent: collapsed ? "center" : "flex-start",
              padding: collapsed ? "10px 0" : "10px 12px",
            }}
          >
            <Icon size={18} color={active ? "#4ADE80" : "rgba(255,255,255,0.5)"} />
            {!collapsed && (
              <>
                <span style={{ marginLeft: 10, flex: 1 }}>{label}</span>
                {active && <ChevronRight size={14} color="#4ADE80" />}
              </>
            )}
          </div>
        );
      })}
    </aside>
  );
}

const styles = {
  sidebar: {
    minHeight: "100vh",
    background: "#1B4332",
    display: "flex",
    flexDirection: "column",
    padding: "24px 12px",
    position: "fixed",
    top: 0, left: 0, bottom: 0,
    zIndex: 100,
    overflowX: "hidden",
    transition: "width 0.25s cubic-bezier(0.4,0,0.2,1)",
  },
  logoRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    cursor: "pointer",
  },
  logoIcon: {
    width: 36, height: 36,
    background: "rgba(255,255,255,0.15)",
    borderRadius: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
    flexShrink: 0,
  },
  logoText: {
    fontSize: 15, fontWeight: 800,
    color: "white", letterSpacing: "-0.3px",
    whiteSpace: "nowrap",
  },
  logoSub: {
    fontSize: 10,
    color: "rgba(255,255,255,0.4)",
    whiteSpace: "nowrap",
  },
  navLabel: {
    fontSize: 10, fontWeight: 700,
    color: "rgba(255,255,255,0.3)",
    letterSpacing: 1.2,
    padding: "0 10px 8px",
    margin: 0,
  },
  navItem: {
    display: "flex", alignItems: "center",
    borderRadius: 8,
    cursor: "pointer",
    fontSize: 13.5, fontWeight: 500,
    color: "rgba(255,255,255,0.55)",
    marginBottom: 2,
    transition: "all 0.18s",
    borderLeft: "3px solid transparent",
  },
  navActive: {
    background: "rgba(255,255,255,0.1)",
    color: "white", fontWeight: 700,
    borderLeft: "3px solid #4ADE80",
  },
  footer: {
    marginTop: "auto",
    paddingTop: 16,
    borderTop: "1px solid rgba(255,255,255,0.1)",
    display: "flex", flexDirection: "column",
  },
};