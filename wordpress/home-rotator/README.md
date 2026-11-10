# accesso home page rotator (IAAPA home page update)

A rotating message module that sits directly under the **Powering the Business of Fun** headline on the accesso.com home page, above everything else.

- `accesso-home-rotator.html`: the module. Paste the whole file into one WordPress **Custom HTML** block.
- `preview.html`: a mock of the hero and the module together, for review only. Don't put it on the site.

## Adding it to WordPress

1. Edit the home page and change the hero headline from "The tech behind the wow" to **Powering the Business of Fun**.
2. Directly beneath the headline, add a **Custom HTML** block. In Elementor, use the **HTML** widget. In WPBakery, use **Raw HTML**.
3. Paste in the full contents of `accesso-home-rotator.html`, then preview the page.
4. If a security or optimization plugin strips `<script>` tags from post content, move the `<script>` part into the theme footer, or into a code-snippet plugin such as WPCode.

## How it behaves

- It moves to the next message every 7 seconds. To change that, edit `--acc-dur`.
- Rotation pauses while someone hovers over or tabs into the module. The pause button stops rotation completely, which meets WCAG 2.2.2.
- The labelled tabs show the theme of each message and a progress bar. Arrow keys move between tabs, and visitors can swipe on phones.
- If the visitor's device is set to reduce motion, the module doesn't rotate on its own.
- All slides share one grid cell, so the page doesn't jump when messages change.
- Fonts are inherited from the theme, so the module matches the rest of the site.
- Everything is scoped to `.acc-rot`, so it won't affect other parts of the page.

## Things to change before it goes live

- **Images:** each slide has a placeholder illustration. To use a photo instead, replace the `<svg>…</svg>` inside `acc-rot__media` with `<img src="https://www.accesso.com/wp-content/uploads/…" alt="">`. Use landscape 4:3 images of at least 1200×900. On phones they're cropped to 16:9.
- **Button links:** the links are guesses (`/about-us/`, `/solutions/`, `/solutions/accesso-intelligence/`). Replace them with the real URLs.
- **Colors:** the colors are set in the `--acc-*` variables at the top. To use the light version, add `acc-rot--light` to the `<section>` class.
- **Identity:** I left it out of slide 3 because the brief marks it "(?)". It's still on the slide 4 diagram as "ID", so remove it there too if it isn't confirmed.

## Copy (one headline and one supporting sentence per option)

| # | Theme | Headline | Supporting sentence |
|---|---|---|---|
| 1 | Expertise and experience | Built by people who've run the park. | Many of our team have worked on the operator side, so every accesso solution is designed around what matters to you: delighted guests, higher revenue, longer dwell time and lasting loyalty. |
| 2 | Value multiplied | One partner. Every return. | Delight guests and grow revenue while your teams save time, cut costs and run a more efficient operation. |
| 3 | The complete solution | Everything your venue runs on, from one partner. | Ticketing, queuing, point of sale, distribution, payments and intelligence, built for the experience economy and designed to work as one. |
| 4 | Joining all the dots | Connected systems. Smarter decisions. | Our integrated platform shares data across every touchpoint, and AI turns it into the insight you need to respond to the market and to your guests in real time. |
| 5 | The guest journey | Making their day, even before it's begun. | From the first click to the ride home, accesso is there at every step of the guest's day. |
