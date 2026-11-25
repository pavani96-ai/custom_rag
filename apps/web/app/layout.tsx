import type { ReactNode } from "react";

/**
 * Root layout for the workspace UI.
 * @param props.children The page content rendered inside the layout.
 */
export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
