import { Building2, ShieldCheck } from 'lucide-react';

export function Topbar() {
  return (
    <header className="topbar">
      <div className="topbar-context">
        <Building2 size={17} aria-hidden="true" />
        <span>Legal Metrology Operations</span>
      </div>
      <div className="topbar-status">
        <ShieldCheck size={17} aria-hidden="true" />
        <span>Controlled workspace</span>
      </div>
    </header>
  );
}
