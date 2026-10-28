// Hand-written checks for the five example prompts, written from each prompt's wording, not from any model output.
// Where a prompt leaves something open, the suite states the convention it assumes (shown in the UI) or does not
// test that case at all. A prompt that differs from these by even one character gets no checks.

import { EXAMPLES } from "./facts";

export type Check = {
  call: string; // evaluated with `f` bound to the function under test
  expect: string; // Python literal
  norm?: "tuples" | "groups"; // normalise the result before comparing (see the harness in public/testbench.worker.mjs)
};

export type Suite = {
  /** regex (case-insensitive) picking the function under test among top-level defs; first def if none matches */
  match: string;
  checks: Check[];
  /** what the suite assumes where the prompt is open to interpretation */
  convention?: string;
};

const SUITES: Suite[] = [
  {
    match: "fib",
    convention: "F(0) = 0, F(1) = 1 (the prompt does not fix the indexing)",
    checks: [
      { call: "f(0)", expect: "0" },
      { call: "f(1)", expect: "1" },
      { call: "f(2)", expect: "1" },
      { call: "f(10)", expect: "55" },
      { call: "f(30)", expect: "832040" },
    ],
  },
  {
    match: "palindrom",
    convention: "inputs avoid spaces, which the prompt does not mention",
    checks: [
      { call: 'f("Racecar")', expect: "True" },
      { call: 'f("Madam!")', expect: "True" },
      { call: 'f("No,on")', expect: "True" },
      { call: 'f("Hello.")', expect: "False" },
      { call: 'f("ab")', expect: "False" },
    ],
  },
  {
    match: "merge|interval",
    convention: "result compared as a list of tuples; touching intervals are not tested",
    checks: [
      { call: "f([(1, 3), (2, 6), (8, 10), (15, 18)])", expect: "[(1, 6), (8, 10), (15, 18)]", norm: "tuples" },
      { call: "f([(8, 10), (1, 3), (2, 6)])", expect: "[(1, 6), (8, 10)]", norm: "tuples" },
      { call: "f([(1, 10), (2, 3)])", expect: "[(1, 10)]", norm: "tuples" },
      { call: "f([(5, 7)])", expect: "[(5, 7)]", norm: "tuples" },
      { call: "f([])", expect: "[]", norm: "tuples" },
    ],
  },
  {
    match: "roman",
    checks: [
      { call: 'f("III")', expect: "3" },
      { call: 'f("IV")', expect: "4" },
      { call: 'f("IX")', expect: "9" },
      { call: 'f("LVIII")', expect: "58" },
      { call: 'f("MCMXCIV")', expect: "1994" },
    ],
  },
  {
    match: "anagram|group",
    convention: "group order and word order are ignored; a dict of groups is accepted",
    checks: [
      { call: 'f(["eat", "tea", "tan", "ate", "nat", "bat"])', expect: '[["ate", "eat", "tea"], ["bat"], ["nat", "tan"]]', norm: "groups" },
      { call: 'f(["abc"])', expect: '[["abc"]]', norm: "groups" },
      { call: "f([])", expect: "[]", norm: "groups" },
      { call: 'f(["ab", "ba", "abc"])', expect: '[["ab", "ba"], ["abc"]]', norm: "groups" },
    ],
  },
];

const BY_PROMPT = new Map(EXAMPLES.map((p, i) => [p, SUITES[i]]));

/** The suite for an example prompt (exact text), else null. */
export function suiteFor(prompt: string): Suite | null {
  return BY_PROMPT.get(prompt.trim()) ?? null;
}

export const SUITE_COUNT = SUITES.length;
