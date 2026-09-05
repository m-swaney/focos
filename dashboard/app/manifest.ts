import type { MetadataRoute } from "next";
import { PAGE_COLORS } from "@/lib/theme";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "FOCOS — Family Office Chief Of Staff",
    short_name: "focos",
    description: "Family Office Chief Of Staff",
    start_url: "/",
    display: "standalone",
    background_color: PAGE_COLORS.dark,
    theme_color: PAGE_COLORS.dark,
    icons: [
      { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png", purpose: "any" },
      { src: "/icons/icon-512-maskable.png", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
  };
}
