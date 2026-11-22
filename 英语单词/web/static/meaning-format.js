/* Number meanings at display time; keep original dictionary text and sense pairs. */
function meaningItems(value) {
  return String(value ?? '').replace(/\\n/g, '\n')
    .replace(/\s*([①-⑳㉑-㉟㊱-㊿])/g, '\n$1')
    .split(/\n|[；;]/).map(line => line.trim()
      .replace(/^(?:[①-⑳㉑-㉟㊱-㊿]|\(?\d+[.)、]|[·•])\s*/, '').trim())
    .filter(Boolean);
}
function circledNumber(index) {
  if (index <= 20) return String.fromCodePoint(0x2460 + index - 1);
  if (index <= 35) return String.fromCodePoint(0x3251 + index - 21);
  if (index <= 50) return String.fromCodePoint(0x32b1 + index - 36);
  return `(${index})`;
}
function formatMeanings(value) {
  return meaningItems(value).map((meaning, i) => `${circledNumber(i + 1)} ${meaning}`).join('\n');
}
