import { Archive, Briefcase, ClipboardCheck, LayoutDashboard, Scale } from 'lucide-react';
import { NavLink } from 'react-router-dom';

const navigation = [
  { to: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/instruments', label: 'Instruments', icon: Scale },
  { to: '/jobs', label: 'Jobs', icon: Briefcase },
  { to: '/reports', label: 'Reports', icon: ClipboardCheck },
  { to: '/archive', label: 'Archive', icon: Archive },
];

export function Sidebar() {
  return (
    <aside className="sidebar" aria-label="Primary navigation">
      <div className="brand">
        <div className="brand-mark" aria-hidden="true">M</div>
        <div>
          <span className="brand-name">METRIQ</span>
          <span className="brand-subtitle">NAWI Test &amp; Verification Management</span>
        </div>
      </div>

      <nav className="navigation">
        <span className="nav-label">Operations</span>
        {navigation.map(({ to, label, icon: Icon }) => (
          <NavLink key={to} to={to} className={({ isActive }) => `nav-link${isActive ? ' active' : ''}`}>
            <Icon size={18} strokeWidth={1.8} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        <span className="environment-dot" aria-hidden="true" />
        Regulatory operations workspace
      </div>
    </aside>
  );
}
