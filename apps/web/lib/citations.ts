/** Splits an answer into text and citation markers like [1], so each marker can be a button. */

export type AnswerSegment = { kind: "text"; text: string } | { kind: "cite"; id: number };

/** Turn one bracket group such as "1" or "1, 2" into citation segments joined by ", ". */
function citeSegments(group: string): AnswerSegment[] {
  const ids = group.split(",").map((part) => Number(part.trim()));
  return ids.flatMap((id, index) =>
    index === 0
      ? [{ kind: "cite" as const, id }]
      : [{ kind: "text" as const, text: ", " }, { kind: "cite" as const, id }],
  );
}

/** Split the answer at each [n] or [n, m] marker, keeping the text between markers in order. */
export function splitCitations(text: string): AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(/\[(\d+(?:\s*,\s*\d+)*)\]/g)) {
    const index = match.index ?? 0;
    if (index > last) {
      segments.push({ kind: "text", text: text.slice(last, index) });
    }
    segments.push(...citeSegments(match[1]));
    last = index + match[0].length;
  }
  if (last < text.length) {
    segments.push({ kind: "text", text: text.slice(last) });
  }
  return segments;
}

/** One line of an answer. Bullet lines start with "*" or "-" and the marker is removed. */
export interface AnswerLine {
  bullet: boolean;
  text: string;
}

/** Split an answer into lines, marking the ones that start as bullet points. */
export function answerLines(text: string): AnswerLine[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.length > 0)
    .map((line) => {
      const match = /^[*-]\s+(.*)$/.exec(line);
      return match ? { bullet: true, text: match[1] } : { bullet: false, text: line };
    });
}
