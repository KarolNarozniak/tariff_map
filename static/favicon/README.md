Place your favicon files here. Recommended set:

- favicon.ico (16x16 or 32x32 inside .ico for legacy)
- favicon-16x16.png
- favicon-32x32.png
- apple-touch-icon.png (180x180)
- android-chrome-192x192.png
- android-chrome-512x512.png
- safari-pinned-tab.svg (monochrome SVG)
- site.webmanifest (already provided)

How to generate (ImageMagick on Windows PowerShell):

1) Install ImageMagick, then run:

   magick convert logo.png -resize 32x32   favicon-32x32.png
   magick convert logo.png -resize 16x16   favicon-16x16.png
   magick convert logo.png -resize 180x180 apple-touch-icon.png
   magick convert logo.png -resize 192x192 android-chrome-192x192.png
   magick convert logo.png -resize 512x512 android-chrome-512x512.png
   magick convert logo.png -resize 32x32 favicon.ico

Alternatively use any favicon generator or export directly from your design tool.

After adding files, refresh the page with hard reload (Ctrl+F5).
