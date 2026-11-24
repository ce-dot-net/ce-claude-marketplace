// SYNTHETIC precision fixture for the upvote PHRASE fast-path (lib/evidence.ts upvoteProbe). Hand-written, NOT real user data.
// POS: the whole message is an approval of the previous result (a phrase plus filler only) -> phrase upvote.
// NEG: everything else -> never a phrase upvote (the model may still look at it). Precision first: NEG is the bigger list.
export const POS: string[] = [
  'perfekt', 'Perfekt, danke!', 'perfekt!!', 'das ist perfekt', 'genau richtig', 'genau so, danke', 'super, das klappt',
  'super das klappt', 'klappt jetzt, danke', 'funktioniert jetzt', 'Funktioniert jetzt einwandfrei, danke dir', 'läuft jetzt',
  'gut gemacht', 'hat geklappt, vielen dank', 'danke, das hat geholfen', 'perfect', 'Perfect, thanks!', 'works', 'it works now',
  'that works, thanks', 'works great', 'thanks, that fixed it', 'thanks that fixed it', 'great job', 'well done!', 'nice work, thank you',
  'exactly right', 'spot on', 'nailed it', 'looks good', 'lgtm', 'awesome, it works', 'yes, that works perfectly',
]
export const NEG: string[] = [
  // bare acknowledgements / continuations / bare thanks
  'ok', 'OK', 'okay', 'ja', 'yes', 'weiter', 'mach weiter', 'continue', 'go on', 'danke', 'thanks', 'thank you', 'super', 'gut', 'passt',
  'alright', 'sure', 'cool', 'nice', '👍',
  // questions (also with a phrase)
  'perfekt?', 'is it perfect?', 'does it work?', 'works?', 'funktioniert das jetzt?', 'klappt das?', 'how does it work?',
  'can you explain how it works', 'wie funktioniert das genau', 'warum funktioniert das jetzt',
  // negations and rejections
  'nicht perfekt', 'not perfect', 'das ist nicht perfekt', 'it works not at all', 'klappt nicht', 'funktioniert nicht', 'das ist falsch',
  "doesn't work", 'not working', 'still broken', 'nein', 'no', 'never works', 'kein bisschen perfekt', 'perfekt ist anders',
  // approval plus a new or additional task (new_request)
  'danke, jetzt mach noch die tests', 'perfekt, jetzt noch die doku', 'super das klappt, kannst du noch den linter laufen lassen',
  'thanks that fixed it, now add a test for it', 'great job, please also update the changelog', 'works, but the second file is still old',
  'perfekt, aber die farbe ist falsch', 'looks good, but rename the function', 'genau richtig, dann mach den release', 'perfect, next the docs',
  'it works now, also commit it', 'gut gemacht, als nächstes die migration',
  // sarcasm / mixed
  'Wow, great job, you deleted the whole config. Truly impressive.', 'na super, perfekt kaputt gemacht', 'perfekt, jetzt ist alles weg',
  'great, now nothing works', 'awesome, it broke the build',
  // quoted, mentioned, other topics
  'the ticket says "works for me", can you check', 'schreib "perfekt" in die überschrift', 'excellent question, what about the cache',
  'the word perfect appears twice in the readme', 'I fixed it myself', 'move it to the top of the file', 'perfect forward secrecy für tls einbauen',
  'works directory aufräumen', 'the build works on ci but not locally', 'it works on my machine only',
  // 3b: answers to a question / accepted offers / agreeing with a finding (real-haiku false positives at 0.8)
  'ja, mach das', 'go, und danach die Tests', 'erstmal Option 1', 'ja das ist wichtig', 'los', 'mach es', 'ja bitte', 'go ahead',
  // long or unrelated
  'please fix the domain shift hook so it injects patterns when the file changes', 'refactor the parser into two modules',
]
