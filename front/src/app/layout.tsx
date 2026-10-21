import type { Metadata } from "next";
import { DM_Sans, Geist } from "next/font/google";
import "./globals.css";

const display = Geist({ variable: "--font-display", weight: "500", subsets: ["latin"] });
const body = DM_Sans({ variable: "--font-body", weight: ["400", "500"], subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Grupo Sazón — Screening",
  description: "Agente de cribado de repartidores",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="es" className={`${display.variable} ${body.variable}`}>
      <body>{children}</body>
    </html>
  );
}
