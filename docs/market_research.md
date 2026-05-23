# Similar Tool Research

## Scope

This research checks tools adjacent to the intended workflow:

- user writes the illustration subject, elements, and use case
- style, taste, and technique are selected visually through thumbnails or references
- the tool turns that into generation prompts
- generated outputs are checked against the intended style and improved until they pass

The local project should not compete as a generic image generator. Its core value is a repeatable style-reproduction loop from the 37 local reference images.

## Findings

| Tool / Feature | Relevant Pattern | Gap For This Project |
|---|---|---|
| Midjourney Style Reference | Uses image references to carry colors, medium, textures, lighting, and overall style into a new prompt. Supports style weight and multiple references. | Strong generation feature, but no local extraction of a reusable style fingerprint, no 37-image benchmark, and no pass/fail score against a reference set. |
| Midjourney Moodboards | Lets users curate images into a reusable moodboard style. Useful precedent for thumbnail-based taste selection. | Moodboard becomes a Midjourney-specific code. It does not expose a transparent rubric or generator-independent prompt pack. |
| Midjourney Style Creator | Lets users click thumbnail samples over refinement rounds to create a custom style reference code. | Good UX precedent for preference learning, but locked to Midjourney and optimized for style discovery, not reproducing a fixed local reference set. |
| Adobe Firefly Style Reference | Combines a text prompt with a style reference image; API docs expose a `strength` value from 1 to 100. | Useful control model, but not a local review loop and not a multi-style prompt/evaluation workbench. |
| Canva AI Image Generator / Dream Lab | Offers text-to-image, style options, and reference-image-inspired generation inside a design workflow. | Good for casual production, but style choices are coarse presets and outputs are not evaluated against a reference corpus. |
| Recraft Styles | Provides curated styles and custom styles; style IDs can be reused, including vector-oriented workflows. | Strong pro-design direction, but style definitions are platform-specific and do not produce a transparent 90-point reproduction audit. |
| Freepik Style | Allows custom style definition by prompt, one reference image, or multiple images, intended for consistent on-brand visuals. | Similar “style as reusable asset” concept, but still lacks local metric baselines, visual review sheets, and gate-driven prompt improvement. |
| Image-to-prompt tools | Analyze a reference image and convert it into prompt text. | Useful partial function, but they generally stop at prompt extraction and do not evaluate whether the regenerated image actually matches the reference style. |

## Implications

Existing tools already prove demand for:

- visual style selection instead of manually writing style vocabulary
- reusable styles/moodboards/reference codes
- style strength or intensity controls
- prompt generation from image references

The local tool should therefore avoid being “another prompt generator.” It should specialize in:

- **transparent style fingerprints**: line, shape, palette, texture, composition, person treatment
- **multi-reference grounding**: 37 references grouped into 5 practical 2D styles
- **fixed-subject transfer test**: every style must render the same subject, “コーヒーを持って散歩している人”
- **reviewable scoring**: automatic metrics plus human rubric, 100-point score, 90-point gate
- **iteration artifacts**: next-round constraints generated from metric weakness, style-rank failure, manual low axes, and reviewer notes
- **Codex subscription workflow**: prompt packs and import auditing, not API dependency

## Product Direction

The primary UI should be a prompt/review tool, not an image-generation backend.

1. The user enters subject elements and intended use.
2. The user selects style/taste/technique from thumbnails.
3. The tool composes a prompt from structured subject data plus selected style fingerprint.
4. The user generates images in Codex/ChatGPT under the subscription workflow.
5. The tool imports, audits, scores, and compares outputs.
6. If the gate fails, the tool creates the next prompt round with concrete fixes.

## Source Notes

- Midjourney Style Reference documentation: https://docs.midjourney.com/hc/en-us/articles/32180011136653-Style-Reference
- Midjourney Moodboards documentation: https://docs.midjourney.com/hc/en-us/articles/39193335040013-Moodboards
- Midjourney Style Creator documentation: https://docs.midjourney.com/hc/en-us/articles/41308374558221-Style-Creator
- Adobe Firefly Style Image Reference API documentation: https://developer.adobe.com/firefly-services/docs/firefly-api/guides/concepts/style-image-reference/
- Adobe Firefly style reference tutorial: https://www.adobe.com/learn/firefly/web/generate-image-using-reference-image
- Canva AI Image Generator page: https://www.canva.com/ai-image-generator/
- Recraft styles documentation: https://www.recraft.ai/docs/api-reference/styles
- Recraft styles overview: https://www.recraft.ai/docs/using-recraft/styles/styles-overview
- Freepik Style documentation: https://www.freepik.com/ai/docs/style
- OpenAI Help Center, Creating images in ChatGPT: https://help.openai.com/en/articles/8932459-creating-images-in-chatgpt
