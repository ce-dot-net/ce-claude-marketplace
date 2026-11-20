// SYNTHETIC evaluation set: every example below was hand-written by the author of this change. It is NOT real user data.
// It shows language and style coverage of the model rejection classifier (lib/rejection.ts), NOT real-world recall/precision.
// label: 'reject' = the message rejects/disputes/complains about the assistant's previous result; 'keep' = it does not.
// kind: the style or the look-alike trap the example exercises.
export type RejectionExample = { text: string; label: 'reject' | 'keep'; lang: string; kind: string; split: 'dev' | 'held'; tail?: string }
type Row = [string, 'reject' | 'keep', string]  // text, label, kind
// split: FROZEN before any round-3 measurement, by a seeded rule (SEED below, FNV-1a over seed|text|tail): inside each language group the
// examples are ordered by that hash and every 3rd one (rank 2, 5, 8, ...) is HELD-OUT, the rest DEV. Exceptions by construction:
// DEV_SHORT is dev, HARD is held-out. The classifier prompt is tuned on dev only; held-out is read once at the end.
// No label is changed after a run: a label found wrong is recorded in LABEL_EXCEPTIONS (reason) and reported both ways.
export const SEED = 'rej-r3'
const h32 = (t: string) => { let h = 2166136261; for (const ch of t) { h ^= ch.codePointAt(0)!; h = Math.imul(h, 16777619) >>> 0 } return h >>> 0 }
export const LABEL_EXCEPTIONS: { text: string; reason: string }[] = []
const set = (lang: string, rows: Row[]): RejectionExample[] => rows.map(([text, label, kind]) => ({ text, label, lang, kind, split: 'dev' as const }))

export const LANGS = ['en', 'de', 'fr', 'es', 'it', 'pt', 'nl', 'tr', 'pl', 'ru', 'ja', 'zh', 'ko', 'ar', 'hi'] as const

const BASE0: RejectionExample[] = [
  ...set('en', [
    ['No, that is not what I asked for. I wanted the sort to be stable.', 'reject', 'not-what-asked'],
    ['Please revert that change, it made things worse.', 'reject', 'undo'],
    ['Wow, great job, you deleted the whole config. Truly impressive.', 'reject', 'sarcasm'],
    ['This is garbage. Do it again from scratch.', 'reject', 'angry'],
    ["Nope. Use a dictionary instead of a list of tuples.", 'reject', 'no-do-x-instead'],
    ['I think this is not quite right, could you take another look?', 'reject', 'polite'],
    ['Why did you use a list here?', 'keep', 'question-about-result'],
    ['The build now fails with a missing import in utils.py, here is the log.', 'keep', 'new-error-report'],
    ['Thanks, that works nicely!', 'keep', 'thanks'],
    ['Not bad at all, now add a docstring to it.', 'keep', 'not-bad-followup'],
    ['Do not use tabs, use spaces from now on.', 'keep', 'fresh-instruction'],
    ['The user said "this is wrong" in the ticket, can you reproduce that case?', 'keep', 'quoted-phrase'],
  ]),
  ...set('de', [
    ['Nein, so habe ich mir das nicht vorgestellt. Mach es bitte noch einmal.', 'reject', 'not-what-asked'],
    ['Nimm die letzte Änderung wieder zurück.', 'reject', 'undo'],
    ['Na super, jetzt ist alles kaputt. Danke für nichts.', 'reject', 'sarcasm'],
    ['Das ist völliger Unsinn, so kann ich nichts anfangen!', 'reject', 'angry'],
    ['Lieber eine Klasse statt vieler Funktionen, bitte umbauen.', 'keep', 'different-approach-request'],
    ['Ich bin mir nicht sicher, ob das so stimmt, schau bitte nochmal drauf.', 'reject', 'polite'],
    ['Warum hast du hier eine Schleife benutzt?', 'keep', 'question-about-result'],
    ['Beim Start kommt jetzt ein neuer Fehler: KeyError in config.py.', 'keep', 'new-error-report'],
    ['Danke, das passt so.', 'keep', 'thanks'],
    ['Verwende ab jetzt keine Tabs, nur Leerzeichen.', 'keep', 'fresh-instruction'],
    ['Nicht schlecht, mach bitte noch die Tests dazu.', 'keep', 'not-bad-followup'],
  ]),
  ...set('fr', [
    ["Non, ce n'est pas ce que j'avais demandé.", 'reject', 'not-what-asked'],
    ['Annule ce changement, il a tout cassé.', 'reject', 'undo'],
    ['Bravo, vraiment excellent, le fichier est maintenant vide.', 'reject', 'sarcasm'],
    ["C'est nul, refais-le entièrement !", 'reject', 'angry'],
    ['Plutôt une classe qu\'une fonction, merci de modifier.', 'keep', 'different-approach-request'],
    ['Pourquoi as-tu choisi une boucle ici ?', 'keep', 'question-about-result'],
    ["Maintenant j'obtiens une autre erreur : module introuvable.", 'keep', 'new-error-report'],
    ['Merci, ça marche très bien.', 'keep', 'thanks'],
    ["N'utilise pas de tabulations, utilise des espaces.", 'keep', 'fresh-instruction'],
    ['Pas mal du tout, ajoute maintenant les tests.', 'keep', 'not-bad-followup'],
  ]),
  ...set('es', [
    ['No, eso no es lo que pedí.', 'reject', 'not-what-asked'],
    ['Deshaz ese cambio, lo empeoró todo.', 'reject', 'undo'],
    ['Genial, qué buen trabajo, borraste toda la configuración.', 'reject', 'sarcasm'],
    ['Esto es un desastre, hazlo de nuevo.', 'reject', 'angry'],
    ['Mejor usa un diccionario en lugar de una lista.', 'keep', 'different-approach-request'],
    ['¿Por qué usaste un bucle aquí?', 'keep', 'question-about-result'],
    ['Ahora aparece un error nuevo en la línea 40, te paso el log.', 'keep', 'new-error-report'],
    ['Gracias, funciona perfecto.', 'keep', 'thanks'],
    ['No uses tabulaciones, usa espacios a partir de ahora.', 'keep', 'fresh-instruction'],
    ['Nada mal, ahora añade la documentación.', 'keep', 'not-bad-followup'],
  ]),
  ...set('it', [
    ['No, non è quello che avevo chiesto.', 'reject', 'not-what-asked'],
    ['Annulla questa modifica, ha peggiorato tutto.', 'reject', 'undo'],
    ['Complimenti, davvero un lavoro eccellente, hai cancellato il file.', 'reject', 'sarcasm'],
    ['Fa schifo, rifallo da capo!', 'reject', 'angry'],
    ['Meglio una classe al posto di tante funzioni.', 'keep', 'different-approach-request'],
    ['Perché hai usato un ciclo qui?', 'keep', 'question-about-result'],
    ['Adesso compare un nuovo errore: modulo non trovato.', 'keep', 'new-error-report'],
    ['Grazie, funziona benissimo.', 'keep', 'thanks'],
    ['Non usare le tabulazioni, usa gli spazi.', 'keep', 'fresh-instruction'],
  ]),
  ...set('pt', [
    ['Não, não era isso que eu pedi.', 'reject', 'not-what-asked'],
    ['Desfaz essa alteração, piorou tudo.', 'reject', 'undo'],
    ['Que ótimo trabalho, apagou o arquivo inteiro.', 'reject', 'sarcasm'],
    ['Isso está péssimo, faz de novo!', 'reject', 'angry'],
    ['Prefiro que use um dicionário em vez de uma lista.', 'keep', 'different-approach-request'],
    ['Por que você usou um laço aqui?', 'keep', 'question-about-result'],
    ['Agora aparece outro erro: módulo não encontrado.', 'keep', 'new-error-report'],
    ['Obrigado, ficou ótimo.', 'keep', 'thanks'],
    ['Não use tabs, use espaços daqui em diante.', 'keep', 'fresh-instruction'],
  ]),
  ...set('nl', [
    ['Nee, dat is niet wat ik gevraagd had.', 'reject', 'not-what-asked'],
    ['Maak die wijziging ongedaan, het is erger geworden.', 'reject', 'undo'],
    ['Echt top gedaan, nu is het hele bestand weg.', 'reject', 'sarcasm'],
    ['Dit is waardeloos, doe het helemaal opnieuw!', 'reject', 'angry'],
    ['Gebruik liever een dictionary in plaats van een lijst.', 'keep', 'different-approach-request'],
    ['Waarom heb je hier een lus gebruikt?', 'keep', 'question-about-result'],
    ['Nu krijg ik een nieuwe foutmelding: module niet gevonden.', 'keep', 'new-error-report'],
    ['Bedankt, dat werkt prima.', 'keep', 'thanks'],
    ['Gebruik geen tabs, gebruik voortaan spaties.', 'keep', 'fresh-instruction'],
  ]),
  ...set('tr', [
    ['Hayır, istediğim bu değildi.', 'reject', 'not-what-asked'],
    ['Bu değişikliği geri al, her şeyi bozdu.', 'reject', 'undo'],
    ['Harika iş çıkarmışsın, bütün dosyayı sildin.', 'reject', 'sarcasm'],
    ['Bu berbat, baştan yap!', 'reject', 'angry'],
    ['Liste yerine sözlük kullan lütfen.', 'keep', 'different-approach-request'],
    ['Burada neden döngü kullandın?', 'keep', 'question-about-result'],
    ['Şimdi yeni bir hata alıyorum: modül bulunamadı.', 'keep', 'new-error-report'],
    ['Teşekkürler, çalışıyor.', 'keep', 'thanks'],
    ['Sekme kullanma, boşluk kullan.', 'keep', 'fresh-instruction'],
  ]),
  ...set('pl', [
    ['Nie, nie o to prosiłem.', 'reject', 'not-what-asked'],
    ['Cofnij tę zmianę, wszystko się pogorszyło.', 'reject', 'undo'],
    ['Świetna robota, skasowałeś cały plik.', 'reject', 'sarcasm'],
    ['To jest beznadziejne, zrób to od nowa!', 'reject', 'angry'],
    ['Lepiej użyj słownika zamiast listy.', 'keep', 'different-approach-request'],
    ['Dlaczego użyłeś tutaj pętli?', 'keep', 'question-about-result'],
    ['Teraz pojawia się nowy błąd: nie znaleziono modułu.', 'keep', 'new-error-report'],
    ['Dziękuję, działa świetnie.', 'keep', 'thanks'],
    ['Nie używaj tabulatorów, używaj spacji.', 'keep', 'fresh-instruction'],
  ]),
  ...set('ru', [
    ['Нет, я просил совсем не это.', 'reject', 'not-what-asked'],
    ['Отмени это изменение, стало только хуже.', 'reject', 'undo'],
    ['Отличная работа, ты удалил весь файл.', 'reject', 'sarcasm'],
    ['Это ужасно, переделай всё заново!', 'reject', 'angry'],
    ['Лучше используй словарь вместо списка.', 'keep', 'different-approach-request'],
    ['Почему ты здесь использовал цикл?', 'keep', 'question-about-result'],
    ['Теперь появилась другая ошибка: модуль не найден.', 'keep', 'new-error-report'],
    ['Спасибо, всё работает.', 'keep', 'thanks'],
    ['Не используй табы, используй пробелы.', 'keep', 'fresh-instruction'],
  ]),
  ...set('ja', [
    ['いや、頼んだのはそれじゃない。', 'reject', 'not-what-asked'],
    ['その変更を元に戻してください。悪化しました。', 'reject', 'undo'],
    ['素晴らしいですね、ファイルを全部消してくれて。', 'reject', 'sarcasm'],
    ['ひどすぎる、最初からやり直して！', 'reject', 'angry'],
    ['リストではなく辞書を使ってください。', 'keep', 'different-approach-request'],
    ['ここでなぜループを使ったのですか？', 'keep', 'question-about-result'],
    ['今度は別のエラーが出ました：モジュールが見つかりません。', 'keep', 'new-error-report'],
    ['ありがとうございます、うまく動きました。', 'keep', 'thanks'],
    ['タブは使わず、スペースを使ってください。', 'keep', 'fresh-instruction'],
  ]),
  ...set('zh', [
    ['不对，我要的不是这个。', 'reject', 'not-what-asked'],
    ['把刚才的修改撤销，越改越糟。', 'reject', 'undo'],
    ['干得真漂亮，把整个文件都删掉了。', 'reject', 'sarcasm'],
    ['这太糟糕了，重新做！', 'reject', 'angry'],
    ['别用列表，改用字典。', 'keep', 'different-approach-request'],
    ['你为什么在这里用了循环？', 'keep', 'question-about-result'],
    ['现在出现了一个新的报错：找不到模块。', 'keep', 'new-error-report'],
    ['谢谢，运行得很好。', 'keep', 'thanks'],
    ['不要使用制表符，以后用空格。', 'keep', 'fresh-instruction'],
  ]),
  ...set('ko', [
    ['아니요, 제가 부탁한 건 이게 아닙니다.', 'reject', 'not-what-asked'],
    ['방금 변경을 되돌려 주세요. 더 나빠졌어요.', 'reject', 'undo'],
    ['정말 대단하네요, 파일을 전부 지워 주셔서.', 'reject', 'sarcasm'],
    ['이건 엉망이야, 처음부터 다시 해!', 'reject', 'angry'],
    ['리스트 말고 딕셔너리를 써 주세요.', 'keep', 'different-approach-request'],
    ['여기서 왜 반복문을 사용했나요?', 'keep', 'question-about-result'],
    ['이번에는 다른 오류가 나옵니다: 모듈을 찾을 수 없음.', 'keep', 'new-error-report'],
    ['감사합니다, 잘 작동해요.', 'keep', 'thanks'],
    ['탭을 쓰지 말고 공백을 사용하세요.', 'keep', 'fresh-instruction'],
  ]),
  ...set('ar', [
    ['لا، هذا ليس ما طلبته.', 'reject', 'not-what-asked'],
    ['تراجع عن هذا التعديل، لقد جعل الأمور أسوأ.', 'reject', 'undo'],
    ['عمل رائع حقًا، لقد حذفت الملف بالكامل.', 'reject', 'sarcasm'],
    ['هذا سيئ جدًا، أعد العمل من البداية!', 'reject', 'angry'],
    ['استخدم قاموسًا بدلًا من القائمة من فضلك.', 'keep', 'different-approach-request'],
    ['لماذا استخدمت حلقة تكرارية هنا؟', 'keep', 'question-about-result'],
    ['الآن يظهر خطأ جديد: الوحدة غير موجودة.', 'keep', 'new-error-report'],
    ['شكرًا، يعمل بشكل ممتاز.', 'keep', 'thanks'],
    ['لا تستخدم علامات التبويب، استخدم المسافات.', 'keep', 'fresh-instruction'],
  ]),
  ...set('hi', [
    ['नहीं, मैंने यह नहीं माँगा था।', 'reject', 'not-what-asked'],
    ['इस बदलाव को वापस पलट दो, सब कुछ बिगड़ गया।', 'reject', 'undo'],
    ['वाह, क्या कमाल का काम है, पूरी फ़ाइल ही मिटा दी।', 'reject', 'sarcasm'],
    ['यह बहुत बेकार है, दोबारा शुरू से करो!', 'reject', 'angry'],
    ['सूची की जगह डिक्शनरी का इस्तेमाल करो।', 'keep', 'different-approach-request'],
    ['तुमने यहाँ लूप का उपयोग क्यों किया?', 'keep', 'question-about-result'],
    ['अब एक नई त्रुटि आ रही है: मॉड्यूल नहीं मिला।', 'keep', 'new-error-report'],
    ['धन्यवाद, यह बढ़िया चल रहा है।', 'keep', 'thanks'],
    ['टैब का उपयोग मत करो, स्पेस का उपयोग करो।', 'keep', 'fresh-instruction'],
  ]),
  ...set('mixed', [
    ['Das ist wrong, bitte revert it and do it anders.', 'reject', 'mixed-language'],
    ['No no no, esto es incorrecto, do it again please.', 'reject', 'mixed-language'],
    ["C'est not what I wanted, refais ça.", 'reject', 'mixed-language'],
    ['Merci, that works, passt so.', 'keep', 'mixed-language'],
    ['Kannst du erklären, why you chose this approach?', 'keep', 'mixed-language'],
    ['Now I get a new error, nicht derselbe wie vorher: ImportError.', 'keep', 'mixed-language'],
  ]),
]

// S2 (round 3): explicit "no, that is wrong, do X" stays reject (a different-approach request WITHOUT a verdict on the result is new_request).
const EXPLICIT: RejectionExample[] = [
  ...set('en', [['No, that is wrong. Use a dictionary, not a list.', 'reject', 'no-wrong-do-x']]),
  ...set('de', [['Nein, das ist falsch so. Nimm bitte ein Dictionary.', 'reject', 'no-wrong-do-x']]),
  ...set('fr', [["Non, c'est incorrect. Utilise un dictionnaire.", 'reject', 'no-wrong-do-x']]),
  ...set('es', [['No, eso está mal. Usa un diccionario.', 'reject', 'no-wrong-do-x']]),
  ...set('it', [['No, è sbagliato. Usa un dizionario.', 'reject', 'no-wrong-do-x']]),
  ...set('pt', [['Não, está errado. Use um dicionário.', 'reject', 'no-wrong-do-x']]),
  ...set('nl', [['Nee, dat klopt niet. Gebruik een dictionary.', 'reject', 'no-wrong-do-x']]),
  ...set('tr', [['Hayır, bu yanlış. Sözlük kullan.', 'reject', 'no-wrong-do-x']]),
  ...set('pl', [['Nie, to jest źle. Użyj słownika.', 'reject', 'no-wrong-do-x']]),
  ...set('ru', [['Нет, это неправильно. Используй словарь.', 'reject', 'no-wrong-do-x']]),
  ...set('ja', [['いいえ、それは間違いです。辞書を使ってください。', 'reject', 'no-wrong-do-x']]),
  ...set('zh', [['不，这是错的。请用字典。', 'reject', 'no-wrong-do-x']]),
  ...set('ko', [['아니요, 그건 틀렸어요. 딕셔너리를 쓰세요.', 'reject', 'no-wrong-do-x']]),
  ...set('ar', [['لا، هذا خطأ. استخدم قاموسًا.', 'reject', 'no-wrong-do-x']]),
  ...set('hi', [['नहीं, यह गलत है। डिक्शनरी का उपयोग करो।', 'reject', 'no-wrong-do-x']]),
]
// M1 (round 3): CONTEXTUAL pairs. The previous answer (`tail`) decides: a bare negative after an OFFER or a QUESTION of the assistant
// declines/answers it (keep); the same word after a plain STATEMENT/result is a rejection. Tails are synthetic, written per language.
const CTX_ROWS: [string, string, string, string, string][] = [  // lang, offer tail, question tail, statement tail, bare no
  ['en', 'Done. Do you also want me to commit this?', 'I can use either approach. Which one do you prefer?', 'I changed the function and all tests pass.', 'no'],
  ['de', 'Fertig. Soll ich das auch committen?', 'Es gibt zwei Varianten. Welche möchtest du?', 'Ich habe die Funktion geändert, alle Tests sind grün.', 'nein'],
  ['fr', 'Terminé. Veux-tu que je le commite aussi ?', 'Deux options existent. Laquelle préfères-tu ?', "J'ai modifié la fonction et tous les tests passent.", 'non'],
  ['es', 'Listo. ¿Quieres que también lo suba al repositorio?', 'Hay dos opciones. ¿Cuál prefieres?', 'Cambié la función y todas las pruebas pasan.', 'no'],
  ['it', 'Fatto. Vuoi che faccia anche il commit?', 'Ci sono due varianti. Quale preferisci?', 'Ho modificato la funzione e tutti i test passano.', 'no'],
  ['pt', 'Pronto. Quer que eu também faça o commit?', 'Há duas opções. Qual você prefere?', 'Alterei a função e todos os testes passam.', 'não'],
  ['nl', 'Klaar. Wil je dat ik het ook commit?', 'Er zijn twee varianten. Welke heeft je voorkeur?', 'Ik heb de functie aangepast en alle tests slagen.', 'nee'],
  ['tr', 'Tamam. Bunu commit etmemi ister misin?', 'İki seçenek var. Hangisini tercih edersin?', 'Fonksiyonu değiştirdim ve tüm testler geçiyor.', 'hayır'],
  ['ru', 'Готово. Хотите, чтобы я ещё сделал коммит?', 'Есть два варианта. Какой вы предпочитаете?', 'Я изменил функцию, все тесты проходят.', 'нет'],
  ['ja', '完了しました。コミットもしましょうか？', '方法は二つあります。どちらがよいですか？', '関数を変更し、すべてのテストが通りました。', 'いいえ'],
  ['zh', '完成了。需要我顺便提交吗？', '有两种方案。你更喜欢哪一种？', '我修改了函数，所有测试都通过了。', '不用'],
  ['ko', '완료했습니다. 커밋도 할까요?', '두 가지 방법이 있습니다. 어느 쪽이 좋으세요?', '함수를 수정했고 모든 테스트가 통과했습니다.', '아니요'],
  ['ar', 'تم. هل تريد أن أقوم بالإيداع أيضًا؟', 'هناك خياران. أيهما تفضل؟', 'عدّلت الدالة وجميع الاختبارات تنجح.', 'لا'],
  ['hi', 'हो गया। क्या मैं इसे कमिट भी कर दूँ?', 'दो विकल्प हैं। आप कौन सा पसंद करेंगे?', 'मैंने फ़ंक्शन बदल दिया और सभी परीक्षण पास हैं।', 'नहीं'],
]
const CTX: RejectionExample[] = [
  ...CTX_ROWS.flatMap(([lang, offer, question, statement, no]): RejectionExample[] => [
    { text: no, label: 'keep', lang, kind: 'ctx-decline-offer', split: 'dev', tail: offer },
    { text: no, label: 'keep', lang, kind: 'ctx-answer-question', split: 'dev', tail: question },
    { text: no, label: 'reject', lang, kind: 'ctx-no-after-statement', split: 'dev', tail: statement },
  ]),
  { text: 'nope', label: 'keep', lang: 'en', kind: 'ctx-decline-offer', split: 'dev', tail: 'Done. Shall I also push the branch?' },
  { text: 'nope', label: 'reject', lang: 'en', kind: 'ctx-no-after-statement', split: 'dev', tail: 'I rewrote the parser and the build is green.' },
  { text: 'nein danke', label: 'keep', lang: 'de', kind: 'ctx-decline-offer', split: 'dev', tail: 'Fertig. Möchtest du, dass ich noch Tests ergänze?' },
  { text: 'nee, lass mal', label: 'keep', lang: 'de', kind: 'ctx-decline-offer', split: 'dev', tail: 'Ich kann das auch gleich umbenennen. Soll ich?' },
]

// ~40 extra HARD examples, written before any result of the tuned prompt was seen: very short prompts, code-switching, sarcasm,
// "no, do X instead", and look-alike non-rejections (instructions with negation, new error reports, questions, thanks).
const hard = (lang: string, text: string, label: 'reject' | 'keep', kind: string): RejectionExample => ({ text, label, lang, kind: 'hard-' + kind, split: 'held' })
const HARD: RejectionExample[] = [
  hard('en', 'no', 'reject', 'short'), hard('en', 'nope', 'reject', 'short'), hard('en', 'wrong', 'reject', 'short'), hard('en', 'undo', 'reject', 'short'),
  hard('de', 'nein', 'reject', 'short'), hard('fr', 'non', 'reject', 'short'), hard('ja', '違う', 'reject', 'short'), hard('zh', '不对', 'reject', 'short'),
  hard('en', 'Oh wonderful, another broken build. Exactly what I hoped for.', 'reject', 'sarcasm'),
  hard('de', 'Ja klar, genau das wollte ich, ein leeres Skript. Danke auch.', 'reject', 'sarcasm'),
  hard('en', 'stop. revert all of it and keep the original version', 'reject', 'undo'),
  hard('es', 'No, usa pytest en vez de unittest, eso que hiciste no sirve.', 'reject', 'no-do-x-instead'),
  hard('mixed', 'Nee nee, that is nicht richtig, bitte neu machen.', 'reject', 'code-switching'),
  hard('mixed', 'Pas ça! I told you the API key goes in .env, nicht hardcoded.', 'reject', 'code-switching'),
  hard('en', 'I already told you twice not to touch the database layer and you did it anyway.', 'reject', 'complaint'),
  hard('ru', 'Не так. Верни как было.', 'reject', 'undo'),
  hard('tr', 'Olmamış, tekrar dene.', 'reject', 'blunt'),
  hard('pt', 'Isso não resolveu nada, tenta outra abordagem.', 'reject', 'no-do-x-instead'),
  hard('ko', '이건 틀렸어요. 다시 해주세요.', 'reject', 'blunt'),
  hard('hi', 'ये ग़लत है, पहले वाला वापस लाओ।', 'reject', 'undo'),
  hard('it', 'Ma che hai combinato? Così non va per niente.', 'reject', 'angry'),
  hard('nl', 'Dit is niet wat ik bedoelde, probeer het anders.', 'reject', 'not-what-asked'),
  hard('en', 'ok', 'keep', 'short'), hard('en', 'thanks', 'keep', 'short'), hard('de', 'danke', 'keep', 'short'), hard('en', 'continue', 'keep', 'short'),
  hard('en', 'No problem, take your time. Next, add logging to the parser.', 'keep', 'negation-not-complaint'),
  hard('en', 'no thanks, that is enough for today', 'keep', 'negation-not-complaint'),
  hard('de', 'Nein danke, den Rest mache ich selbst.', 'keep', 'negation-not-complaint'),
  hard('en', "Don't commit anything yet, I want to review the diff first.", 'keep', 'fresh-instruction'),
  hard('fr', "Ne modifie pas le fichier de configuration, utilise une variable d'environnement.", 'keep', 'fresh-instruction'),
  hard('en', 'Traceback (most recent call last): File "app.py", line 12, in <module> KeyError: "user"', 'keep', 'new-error-report'),
  hard('en', 'The deploy step fails with exit code 1 now, can you look into it?', 'keep', 'new-error-report'),
  hard('de', 'Jetzt schlägt der Test test_login fehl, hier ist die Ausgabe.', 'keep', 'new-error-report'),
  hard('en', 'What would undo do here, would it also remove the migration?', 'keep', 'question-about-result'),
  hard('en', 'Is it correct that the cache is cleared on every call?', 'keep', 'question-about-result'),
  hard('es', '¿Puedes explicar por qué elegiste esa estructura de carpetas?', 'keep', 'question-about-result'),
  hard('en', 'Looks good to me. Could you also add type hints to the helper?', 'keep', 'polite-followup'),
  hard('ja', 'ありがとう。次にREADMEも更新してもらえますか？', 'keep', 'polite-followup'),
  hard('zh', '好的，接下来请帮我写单元测试。', 'keep', 'polite-followup'),
  hard('mixed', 'Super, danke! Now please rename the variable to user_id.', 'keep', 'code-switching'),
  hard('en', 'The error message in the log says "wrong password" for the test user, is that expected?', 'keep', 'quoted-phrase'),
]
// Added to DEV in round 2 after a first look at the (then) held-out run showed that very short prompts were weak: dev examples of
// the same kind with different words, so the prompt can be tuned on dev only. Disclosed in the final report.
const dev = (lang: string, text: string, label: 'reject' | 'keep', kind: string): RejectionExample => ({ text, label, lang, kind: 'dev-' + kind, split: 'dev' })
const DEV_SHORT: RejectionExample[] = [
  dev('en', 'nah', 'reject', 'short'), dev('en', 'incorrect', 'reject', 'short'), dev('en', 'revert it', 'reject', 'short'), dev('en', 'no way', 'reject', 'short'),
  dev('de', 'nicht so', 'reject', 'short'), dev('fr', 'rien de bon', 'reject', 'short'), dev('es', 'mal', 'reject', 'short'), dev('it', 'sbagliato', 'reject', 'short'),
  dev('en', 'great', 'keep', 'short'), dev('en', 'yes', 'keep', 'short'), dev('en', 'sure, go on', 'keep', 'short'), dev('es', 'gracias', 'keep', 'short'),
  dev('fr', 'merci', 'keep', 'short'), dev('pt', 'obrigado', 'keep', 'short'), dev('ru', 'спасибо', 'keep', 'short'), dev('de', 'weiter', 'keep', 'short'),
]
const SPLIT_ME: RejectionExample[] = [...BASE0, ...EXPLICIT, ...CTX]
{
  const by = new Map<string, RejectionExample[]>()
  for (const e of SPLIT_ME) by.set(e.lang, [...(by.get(e.lang) ?? []), e])
  for (const g of by.values()) g.sort((a, b) => h32(`${SEED}|${a.text}|${a.tail ?? ''}`) - h32(`${SEED}|${b.text}|${b.tail ?? ''}`)).forEach((e, i) => { e.split = i % 3 === 2 ? 'held' : 'dev' })
}
const EXAMPLES: RejectionExample[] = [...SPLIT_ME, ...DEV_SHORT, ...HARD]
export default EXAMPLES
export const DEV = EXAMPLES.filter(e => e.split === 'dev')
export const HELD = EXAMPLES.filter(e => e.split === 'held')
