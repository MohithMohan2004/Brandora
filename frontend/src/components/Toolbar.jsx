import { createContext, useContext } from "react";
import Icon from "../icons.jsx";

// Lets any view's toolbar open the sidebar on phones.
export const ShellContext = createContext({ openNav: () => {} });

// Translucent, sticky: the content scrolls underneath it.
export default function Toolbar({ title, subtitle, children, leading }) {
  const { openNav } = useContext(ShellContext);
  return (
    <header className="toolbar material">
      <button className="icon-btn nav-toggle" onClick={openNav} aria-label="Open sidebar" title="Sidebar">
        <Icon name="sidebar" size={20} />
      </button>
      {leading}
      <div className="toolbar-title">
        <h1>{title}</h1>
        {subtitle && <p>{subtitle}</p>}
      </div>
      <div className="toolbar-actions">{children}</div>
    </header>
  );
}
