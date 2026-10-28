/** Static export for S3 + CloudFront. trailingSlash gives /notes/index.html, which the CloudFront function maps. */
export default {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
  poweredByHeader: false,
};
