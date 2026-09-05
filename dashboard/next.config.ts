import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  redirects: async () => [
    { source: "/entities", destination: "/wealth", permanent: false },
    { source: "/alerts", destination: "/", permanent: false },
    { source: "/system", destination: "/", permanent: false },
  ],
};

export default nextConfig;
