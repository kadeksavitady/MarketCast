import { Link, useLocation } from "react-router-dom";

function Navbar() {
  const location = useLocation();

  const navStyle = {
    backgroundColor: "#1a472a",
    padding: "0 24px",
    display: "flex",
    alignItems: "center",
    gap: "32px",
    height: "60px",
  };

  const brandStyle = {
    color: "white",
    fontWeight: "bold",
    fontSize: "20px",
    textDecoration: "none",
  };

  const linkStyle = (path) => ({
    color: location.pathname === path ? "#4ade80" : "#d1fae5",
    textDecoration: "none",
    fontWeight: location.pathname === path ? "600" : "400",
    borderBottom: location.pathname === path ? "2px solid #4ade80" : "none",
    paddingBottom: "4px",
  });

  return (
    <nav style={navStyle}>
      <Link to="/" style={brandStyle}>
        🌾 MarketCast
      </Link>
      <Link to="/" style={linkStyle("/")}>Dashboard</Link>
      <Link to="/simulasi" style={linkStyle("/simulasi")}>Simulasi Belanja</Link>
      <Link to="/tren" style={linkStyle("/tren")}>Tren Harga</Link>
    </nav>
  );
}

export default Navbar;