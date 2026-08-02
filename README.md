# Nuvio-assets

Self-hosted artwork for the Nuvio collections. Every `coverImageUrl` / `titleLogoUrl` /
`heroBackdropUrl` / `focusGifUrl` in `nuvio-collections.json` and `nuvio-collections-PT.json`
points here, so **moving or renaming anything in this repo breaks those two files.**

## Layout

```
<collection>/<folder>/backdrop.webp          always at the root — never localised
<collection>/<folder>/en/{cover,movie,title}.webp
<collection>/<folder>/pt/{cover,movie,title}.webp
```

Collections: `streaming-services`, `genres`, `decades`, `moods`, `international-cinema`.
`anime/` and `discovery/` serve other app surfaces and are not referenced by the collection files.

The two collection files resolve against this layout:

| file | rule |
|---|---|
| `nuvio-collections.json` | `en/<asset>` if it exists, else the root path |
| `nuvio-collections-PT.json` | `pt/<asset>`, else `en/<asset>`, else the root path |

## Folders that are single-language on purpose

These are **not** gaps — don't "complete" them:

| what | why |
|---|---|
| all of `streaming-services` | brand names; no `en/`–`pt/` split at all |
| `genres/`: anime, crime, drama, reality-tv, romance, stand-up-comedy, thriller | the word is identical in both languages, so the art stays at the folder root |
| `genres/romantic-comedy`, `genres/science-fiction` | only `pt/title.webp` exists — cover and movie deliberately keep the English ROM-COM / SCI-FI |
| `decades/*` cover + movie | they show a numeral ("80s"); only the title logo is localised |
| `moods/*` | no title asset exists in the design — cover + movie only |

## Notes

- Stills are `.webp`. Only the 13 streaming focus assets are genuinely animated `.gif`.
- `scripts/build_backdrop.py` regenerates a backdrop from TMDB. Needs a venv — system
  Python on macOS refuses pip under PEP 668.
- Verify links against `git ls-tree -r origin/main`, not the working tree: unpushed is a 404.
