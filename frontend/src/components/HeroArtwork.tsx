// Provided artwork (public/images). Decorative: headline text carries the meaning.
// Not mirrored for LTR (it contains a letter). Text always sits on the physical right side, over the sunset sky.
const BASE = '/images/sheetcraft-sunset-excel'
export default function HeroArtwork() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 h-82.5 md:inset-0 md:h-full">
      <picture>
        <source type="image/webp" srcSet={`${BASE}-900.webp 900w, ${BASE}.webp 1672w`} sizes="100vw" />
        <img src={`${BASE}.png`} width={1672} height={941} alt="" fetchPriority="high" decoding="async"
          className="h-full w-full object-cover [object-position:18%_40%] md:[object-position:12%_68%]" />
      </picture>
      {/* readability: darken only the text side (physical right) */}
      <div className="hero-fade absolute inset-0 hidden md:block" />
      {/* mobile: blend the image into the navy text area */}
      <div className="absolute inset-x-0 bottom-0 h-32 bg-linear-to-b from-transparent to-navy md:hidden" />
      <div className="absolute inset-x-0 top-0 h-24 bg-linear-to-b from-navy/70 to-transparent" />
    </div>
  )
}
