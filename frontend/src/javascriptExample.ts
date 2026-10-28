export const javascriptExample = `// HTML уже очищен от script/style и активных вложений.
const md = toMarkdown(document.html);
saveMarkdown('page.md', md);

// Найти строку Markdown, затем привязать значение к исходному блоку.
const prefix = params.prefix || 'Владелец:';
const line = md.split(/\\r?\\n/).find(line => line.includes(prefix));
if (line) {
  const block = document.blocks.find(b => b.text.includes(prefix));
  if (block) {
    const value = block.text.slice(block.text.indexOf(prefix) + prefix.length).trim();
    emit(params.field || 'owner', value, [block.id]);
    warnings.push('Найдено значение: ' + value);
  }
} else {
  warnings.push('Строка с префиксом ' + prefix + ' не найдена');
}`;
