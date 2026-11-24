import { NavLink, Outlet } from 'react-router';
import { useEffect, useState } from 'react';
import { Badge, Button, Sheet, SheetContent, SheetHeader, SheetTitle, useIsMobile } from '@databricks/appkit-ui/react';
import { Menu } from 'lucide-react';
import { ThemeToggle } from './ThemeToggle';

const links = [
  { to: '/', label: 'Launch Portfolio', end: true },
  { to: '/actions', label: 'Action Center' },
  { to: '/advisor', label: 'Mitigation Advisor' },
  { to: '/ask', label: 'Ask the Data' },
];
const cls = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm font-medium border-b-2 transition-colors ${
    isActive ? 'border-primary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'
  }`;

export function useWhoAmI() {
  const [me, setMe] = useState<{ email?: string | null } | null>(null);
  useEffect(() => {
    fetch('/api/whoami').then((r) => (r.ok ? r.json() : null)).then(setMe).catch(() => setMe(null));
  }, []);
  return me;
}

export function Shell() {
  const isMobile = useIsMobile();
  const [open, setOpen] = useState(false);
  const me = useWhoAmI();
  return (
    <div className="min-h-screen bg-background flex flex-col">
      <header className="bg-card border-b">
        <div className="h-1 bg-primary" />
        <div className="max-w-[1400px] mx-auto px-4 md:px-6 flex items-center gap-4 h-14">
          <div className="flex items-center gap-3 shrink-0">
            <span className="brand-wordmark text-3xl leading-none">Altura</span>
            <div className="h-7 w-px bg-border" />
            <div className="leading-tight">
              <div className="text-sm font-semibold text-foreground">NPI Launch Readiness</div>
              <div className="text-[11px] text-muted-foreground">Bonding &amp; Tapes · Supply Chain</div>
            </div>
          </div>
          <nav className="hidden md:flex gap-1 ml-6 self-stretch items-end">
            {links.map((l) => (
              <NavLink key={l.to} to={l.to} end={l.end} className={cls}>
                {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <Badge variant="outline" className="hidden sm:inline-flex">{me?.email ?? 'Signed in'}</Badge>
            <ThemeToggle />
            {isMobile && (
              <Sheet open={open} onOpenChange={setOpen}>
                <Button variant="ghost" size="icon" onClick={() => setOpen(true)} aria-label="Open navigation">
                  <Menu className="h-5 w-5" />
                </Button>
                <SheetContent side="left">
                  <SheetHeader><SheetTitle>Navigation</SheetTitle></SheetHeader>
                  <nav className="flex flex-col gap-1 p-4">
                    {links.map((l) => (
                      <NavLink key={l.to} to={l.to} end={l.end} className={cls} onClick={() => setOpen(false)}>
                        {l.label}
                      </NavLink>
                    ))}
                  </nav>
                </SheetContent>
              </Sheet>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 w-full max-w-[1400px] mx-auto p-4 md:p-6">
        <Outlet />
      </main>
      <footer className="border-t text-xs text-muted-foreground">
        <div className="max-w-[1400px] mx-auto px-4 md:px-6 py-3 flex flex-wrap gap-x-4 gap-y-1 justify-between">
          <span>Demonstration build · all products, suppliers, OEMs and figures are synthetic</span>
          <span>Lakeflow → Unity Catalog → ML &amp; GenAI → Lakebase → Databricks App · Built on Databricks</span>
        </div>
      </footer>
    </div>
  );
}
