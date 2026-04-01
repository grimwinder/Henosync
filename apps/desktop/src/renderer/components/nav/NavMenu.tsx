import { Home, Map } from "lucide-react";
import type { AppPage } from "../../types/ui";

interface NavItem {
  id: AppPage;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { id: "home", label: "Home", icon: <Home size={18} /> },
  { id: "zones", label: "Zones", icon: <Map size={18} /> },
];

interface NavMenuProps {
  activePage: AppPage;
  onNavigate: (page: AppPage) => void;
}

export default function NavMenu({ activePage, onNavigate }: NavMenuProps) {
  return (
    <div
      style={{
        width: "52px",
        height: "100%",
        backgroundColor: "#141619",
        borderRight: "1px solid #2A2F38",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        paddingTop: "8px",
        flexShrink: 0,
      }}
    >
      {NAV_ITEMS.map((item) => {
        const active = activePage === item.id;
        return (
          <button
            key={item.id}
            title={item.label}
            onClick={() => onNavigate(item.id)}
            style={{
              width: "36px",
              height: "36px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "6px",
              border: "none",
              cursor: "pointer",
              marginBottom: "4px",
              backgroundColor: active ? "#1C1F24" : "transparent",
              color: active ? "#4A9EFF" : "#8B95A3",
              transition: "background-color 150ms, color 150ms",
            }}
            onMouseEnter={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "#1C1F24";
                (e.currentTarget as HTMLButtonElement).style.color = "#E8EAED";
              }
            }}
            onMouseLeave={(e) => {
              if (!active) {
                (e.currentTarget as HTMLButtonElement).style.backgroundColor =
                  "transparent";
                (e.currentTarget as HTMLButtonElement).style.color = "#8B95A3";
              }
            }}
          >
            {item.icon}
          </button>
        );
      })}
    </div>
  );
}
