import type { ParseDialogueFn } from "../types/dialogue";

/**
 * STUB parseDialogue — chỉ trả về cấu trúc rỗng để UI có thể nối dây.
 * TODO: detect "[Name]: line", gom characters unique, build utterances, issues.
 */
export const parseDialogue: ParseDialogueFn = (input) => {
  // TODO: trim, split lines (CRLF/LF), validate "name: text"
  // TODO: push issues cho dòng sai form thay vì throw
  return { characters: [], utterances: [], issues: input ? [] : [] };
};
