import { useLocation, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  TrendingUp,
  History,
  Settings,
  ShoppingBasket,
} from "lucide-react";

const navItems = [
  { id: "/", icon: LayoutDashboard, label: "Dashboard" },
  { id: "/tren", icon: TrendingUp, label: "Market Trends" },
  { id: "/history", icon: History, label: "Simulation History" },
];

export default function Sidebar() {
  const location = useLocation();
  const navigate = useNavigate();

  return (
    <aside style={styles.sidebar}>
      {/* Logo */}
      <div style={styles.logo}>
        <div style={styles.logoIcon}>
          <ShoppingBasket size={20} color="white" />
        </div>
        <span style={styles.logoText}>MarketCast</span>
      </div>

      {/* Nav */}
      <div style={styles.navLabel}>MENU</div>
      {navItems.map((item) => {
        const active = location.pathname === item.id;
        const Icon = item.icon;
        return (
          <div
            key={item.id}
            onClick={() => navigate(item.id)}
            style={{
              ...styles.navItem,
              ...(active ? styles.navItemActive : {}),
            }}
          >
            <Icon size={16} color={active ? "var(--primary-dark)" : "var(--text-sub)"} />
            <span>{item.label}</span>
          </div>
        );
      })}

      {/* Footer */}
      <div style={styles.sidebarFooter}>
        <div style={styles.navItem}>
          <Settings size={16} color="var(--text-sub)" />
          <span>Settings</span>
        </div>
      </div>
    </aside>
  );
}

const styles = {
  sidebar: {
    width: 230,
    minHeight: "100vh",
    background: "var(--sidebar-bg)",
    borderRight: "1px solid var(--border)",
    display: "flex",
    flexDirection: "column",
    padding: "24px 16px",
    position: "fixed",
    top: 0, left: 0, bottom: 0,
    zIndex: 100,
  },
  logo: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "0 8px 28px",
  },
  logoIcon: {
    width: 36, height: 36,
    background: "linear-gradient(135deg, var(--primary), var(--primary-dark))",
    borderRadius: 10,
    display: "flex", alignItems: "center", justifyContent: "center",
  },
  logoText: {
    fontSize: 17,
    fontWeight: 800,
    color: "var(--text-main)",
    letterSpacing: "-0.3px",
  },
  navLabel: {
    fontSize: 10,
    fontWeight: 700,
    color: "var(--text-muted)",
    letterSpacing: 1,
    padding: "0 10px 8px",
  },
  navItem: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "10px 12px",
    borderRadius: "var(--radius-sm)",
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 500,
    color: "var(--text-sub)",
    marginBottom: 2,
    transition: "all 0.18s",
  },
  navItemActive: {
    background: "var(--primary-light)",
    color: "var(--primary-dark)",
    fontWeight: 700,
  },
  sidebarFooter: {
    marginTop: "auto",
    paddingTop: 16,
    borderTop: "1px solid var(--border)",
  },
};