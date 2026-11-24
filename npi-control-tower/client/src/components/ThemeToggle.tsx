import { useEffect, useState } from 'react';
import { Button } from '@databricks/appkit-ui/react';
import { Moon, Sun } from 'lucide-react';

type Theme = 'light' | 'dark';
const KEY = 'npi-theme';

function current(): Theme {
  return document.documentElement.classList.contains('dark') ? 'dark' : 'light';
}

/** Light / dark switch. Light (Altura brand) is the default; the choice is remembered per browser. */
export function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => current());
  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle('dark', theme === 'dark');
    root.classList.toggle('light', theme === 'light');
    try { localStorage.setItem(KEY, theme); } catch { /* storage unavailable: keep for this session */ }
  }, [theme]);
  const next: Theme = theme === 'dark' ? 'light' : 'dark';
  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(next)}
            aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}>
      {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </Button>
  );
}
