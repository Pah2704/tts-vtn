/**
 * Module Z — Cấu trúc hội thoại sau parse + chữ ký hàm parseDialogue (type).
 * Dùng cú pháp: [Nhân vật]: Lời thoại
 */

export interface ParseIssue {
  /** dòng tính từ 1; 0 nếu không xác định. */
  readonly line: number;
  /** mô tả ngắn gọn vấn đề (thiếu ':', tên rỗng, v.v.). */
  readonly message: string;
}

/** Một câu thoại đã parse. */
export interface Utterance {
  /** tên nhân vật đã chuẩn hoá (trim). */
  readonly speaker: string;
  /** nội dung lời thoại nguyên văn sau khi trim. */
  readonly text: string;
  /** chỉ số câu theo thứ tự xuất hiện, bắt đầu từ 0. */
  readonly index: number;
}

/** Kết quả parse toàn bộ văn bản hội thoại. */
export interface ParsedDialogue {
  /** Danh sách nhân vật duy nhất theo thứ tự xuất hiện. */
  readonly characters: ReadonlyArray<string>;
  /** Tất cả câu thoại tuyến tính. */
  readonly utterances: ReadonlyArray<Utterance>;
  /** Lỗi/khuyến nghị (nếu có), không chặn render basic. */
  readonly issues?: ReadonlyArray<ParseIssue>;
}

/**
 * Chữ ký hàm parseDialogue (chỉ type; implementation ở bước (5) trong src/lib/parser.ts).
 *
 * INTENT:
 *  - Chuyển plain text thành cấu trúc hội thoại dựa trên cú pháp "[Name]: line".
 *
 * PRE:
 *  - input có thể chứa dòng trống; CRLF/LF đều được.
 *  - Một dòng hợp lệ phải có phần "Tên" (>=1 ký tự không phải dấu ':') + dấu ':' rồi tới lời thoại (có thể rỗng).
 *
 * POST:
 *  - Trả ParsedDialogue với `characters` duy nhất, `utterances` theo thứ tự.
 *  - Không throw cho lỗi cú pháp nhẹ; thay vào đó ghi vào `issues`.
 *
 * ERROR CASES:
 *  - Nếu input quá dài (ví dụ > 20k ký tự tuỳ FE/BE), implementation có thể throw hoặc cắt bớt (sẽ quyết ở bước (5/9)).
 */
export type ParseDialogueFn = (input: string) => ParsedDialogue;