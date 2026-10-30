export type Lang = 'ar' | 'en'
export type TabId = 'quick' | 'finance' | 'staff' | 'inventory' | 'reports' | 'edu'
export interface Example { id: string; label: string; sub: string; prompt: string }
const ex = (id: string, ar: [string, string, string], en: [string, string, string]) => ({
  ar: { id, label: ar[0], sub: ar[1], prompt: ar[2] }, en: { id, label: en[0], sub: en[1], prompt: en[2] } })
const E = [
  ex('expenses', ['جدول مصاريف الشهر', 'التاريخ - التصنيف - الوصف - المبلغ', 'أنشئ جدول مصروفات شهرية بالتاريخ والفئة والوصف والمبلغ، مع إجمالي المصروفات ومجموع كل فئة.'],
    ['Monthly expenses', 'Date - Category - Description - Amount', 'Create a monthly expenses sheet with date, category, description and amount, plus total spend and a sum per category.']),
  ex('inventory', ['قائمة مخزون المنتجات', 'الاسم - الكمية - السعر - الإجمالي', 'أنشئ جدول مخزون بالمنتج والكمية وسعر الوحدة، مع قيمة المخزون الإجمالية.'],
    ['Product inventory', 'Name - Quantity - Price - Total', 'Create an inventory sheet with product, quantity and unit price, with total stock value.']),
  ex('attendance', ['جدول حضور الموظفين', 'الاسم - التاريخ - الحالة - الملاحظات', 'أنشئ نموذج حضور للموظفين بالاسم والتاريخ والحالة، واحسب عدد أيام الحضور والغياب لكل موظف.'],
    ['Employee attendance', 'Name - Date - Status - Notes', 'Create an employee attendance template with name, date and status, and count present and absent days.']),
  ex('grades', ['جدول درجات الطلاب', 'الاسم - المادة - الدرجة - التقدير', 'أنشئ جدول درجات الطلاب بالاسم والمادة والدرجة، مع المتوسط ونسبة النجاح.'],
    ['Student grades', 'Name - Subject - Score - Grade', 'Create a student grades sheet with name, subject and score, with the average and the pass rate.']),
  ex('sales', ['تقرير المبيعات', 'المنتج - المنطقة - الكمية - الإيراد', 'أنشئ تقرير مبيعات بالمنتج والمنطقة والكمية والإيراد، مع الإجماليات حسب المنطقة.'],
    ['Sales report', 'Product - Region - Units - Revenue', 'Create a sales report with product, region, units and revenue, with totals by region.']),
  ex('tasks', ['مهام المشروع', 'المهمة - المسؤول - الحالة - التسليم', 'أنشئ جدول مهام مشروع بالمهمة والمسؤول والحالة وتاريخ التسليم، مع عدد المهام المكتملة.'],
    ['Project tasks', 'Task - Owner - Status - Due date', 'Create a project task tracker with task, owner, status and due date, with the number of completed tasks.']),
]
export const EXAMPLES: Record<Lang, Example[]> = { ar: E.map(e => e.ar), en: E.map(e => e.en) }
// tab -> example id (tabs fill the prompt with an editable request)
export const TAB_EXAMPLE: Record<TabId, string> = { quick: 'expenses', finance: 'expenses', staff: 'attendance', inventory: 'inventory', reports: 'sales', edu: 'grades' }

export const T = {
  ar: {
    nav: ['الرئيسية', 'الميزات', 'أمثلة', 'حول'], tagline: 'من وصفك إلى جدول احترافي', toggleLang: 'English', theme: 'تبديل المظهر',
    badge: 'ذكاء اصطناعي • سهل • سريع', h1a: 'حوّل أفكارك إلى جداول', h1b: 'Excel احترافية',
    sub: 'اكتب ما تحتاجه بلغة طبيعية، ودع الذكاء الاصطناعي ينشئ لك جدولًا منظمًا بصيغة Excel جاهزًا للتنزيل.',
    inds: [['جداول منظمة', 'ومرتبة'], ['تنزيل مباشر', 'ملف Excel'], ['دعم العربية', 'والإنجليزية']],
    tabs: [['quick', 'أمثلة سريعة'], ['finance', 'المالية'], ['staff', 'الموظفين'], ['inventory', 'المخزون'], ['reports', 'التقارير'], ['edu', 'التعليم']] as [TabId, string][],
    aiChip: 'موجز بالذكاء الاصطناعي', placeholder: 'اكتب وصفك هنا...', clear: 'مسح النص', language: 'اللغة', rows: 'عدد الصفوف (تقريبي)',
    rowsHint: (m: number) => `الحد الأقصى ${m.toLocaleString('ar-EG')} صف`,
    create: 'إنشاء Excel', creating: 'جارٍ الإنشاء…', tooShort: 'اكتب وصفًا لا يقل عن 3 أحرف.', tooLong: (m: number) => `الحد الأقصى ${m} حرف.`,
    retry: 'إعادة المحاولة', error: 'تعذّر إنشاء الملف.',
    feats: [['تصميم احترافي', 'واجهة عصرية وتجربة استخدام سلسة'], ['مدعوم بالذكاء الاصطناعي', 'يعمل عبر نماذج لغوية مفتوحة'],
      ['سريع وفعّال', 'من الوصف إلى ملف Excel بخطوات بسيطة'], ['آمن ومضبوط', 'تحقق صارم من المدخلات والمعادلات']],
    suggested: 'أمثلة مقترحة', resultTag: 'مثال على النتيجة', exTitle: 'جدول مصاريف الشهر',
    exChecks: ['تنسيق احترافي', 'معادلات تلقائية', 'جاهز للطباعة أو التعديل'], exFile: 'ملف Excel جاهز للتنزيل',
    exCols: ['التاريخ', 'النوع', 'الوصف', 'المبلغ'], exTotal: 'الإجمالي',
    exRows: [['2025-10-01', 'سكن', 'إيجار المنزل', '1200'], ['2025-10-03', 'مواصلات', 'بنزين', '150'], ['2025-10-07', 'طعام', 'مشتريات البقالة', '320'], ['2025-10-12', 'ترفيه', 'مطعم', '180']],
    resultTitle: 'نتيجة الإنشاء',
    done: 'تم إنشاء ملف Excel', downloadBtn: 'تنزيل الملف', cancel: 'إلغاء', warnings: (n: number) => `تم تخطي ${n} عنصرًا غير مدعوم؛ التفاصيل في ورقة «الملخص» داخل الملف.`,
    previewNote: (shown: number, total: number) => `معاينة أول ${shown.toLocaleString('ar-EG')} من ${total.toLocaleString('ar-EG')} صف. الملف يحتوي على كل الصفوف.`,
    colsNote: (shown: number, total: number) => `تُعرض ${shown} من ${total} عمودًا.`, calcsTitle: 'الحسابات المضمّنة في الملف',
    calcNote: 'تُحسب القيم عند فتح الملف في Excel.', syntheticTag: 'بيانات تجريبية', refId: 'المعرّف',
    retryIn: (s: number) => `يمكنك المحاولة بعد حوالي ${s} ثانية.`,
    errors: {
      invalid_request: 'الطلب غير صالح. راجع النص وعدد الصفوف.', payload_too_large: 'الطلب كبير جدًا. اختصر الوصف.', length_required: 'تعذّر إرسال الطلب. حدّث الصفحة وحاول مجددًا.',
      invalid_spec: 'تعذّر فهم الطلب أو تجاوز الحدود المسموحة. أعد صياغته بوضوح أو قلّل الأعمدة/الصفوف.', rate_limited: 'عدد الطلبات كبير. انتظر قليلًا ثم حاول مجددًا.',
      ai_quota: 'استُنفدت حصة الذكاء الاصطناعي المجانية مؤقتًا. حاول لاحقًا.', ai_unavailable: 'خدمة الذكاء الاصطناعي غير متاحة حاليًا.', busy: 'الخادم مشغول حاليًا. حاول مرة أخرى بعد لحظات.',
      timeout: 'استغرق الطلب وقتًا طويلًا. حاول مجددًا (قد يكون الخادم يستيقظ من السكون).', internal_error: 'حدث خطأ غير متوقع في الخادم.',
      network: 'تعذّر الاتصال بالخادم. تحقق من الإنترنت وحاول مجددًا.', aborted: 'أُلغي الطلب.', unknown: 'تعذّر إنشاء الملف.' },
    demoBanner: 'وضع تجريبي (المرحلة 2): البيانات أدناه عيّنة توضيحية ولم يُنشأ ملف حقيقي. التنزيل الفعلي يُفعَّل بعد ربط الخادم.',
    download: 'تنزيل (غير متاح بعد)', demoTag: 'بيانات توضيحية', rowsOf: (n: number) => `${n.toLocaleString('ar-EG')} صف`,
    page: 'صفحة', of: 'من', prev: 'السابق', next: 'التالي', total: 'إجمالي الصفوف', previewTitle: 'معاينة الجدول',
    cols: ['الاسم', 'القسم', 'الراتب', 'الحالة'], ph: 'عنصر', statuses: ['نشط', 'غير نشط'], depts: ['الإدارة', 'المبيعات', 'التقنية'],
    footerBar: 'حوّل أفكارك إلى جداول احترافية مع قوة الذكاء الاصطناعي', footer: 'مشروع قيد التطوير. الخدمات المجانية لها حدود استخدام.'
  },
  en: {
    nav: ['Home', 'Features', 'Examples', 'About'], tagline: 'From your description to a pro spreadsheet', toggleLang: 'العربية', theme: 'Toggle theme',
    badge: 'AI • Easy • Fast', h1a: 'Turn your ideas into', h1b: 'professional Excel sheets',
    sub: 'Describe what you need in plain language and AI prepares a well-organized Excel workbook, ready to download.',
    inds: [['Organized', 'clean tables'], ['Direct download', 'Excel file'], ['Arabic and', 'English support']],
    tabs: [['quick', 'Quick examples'], ['finance', 'Finance'], ['staff', 'Staff'], ['inventory', 'Inventory'], ['reports', 'Reports'], ['edu', 'Education']] as [TabId, string][],
    aiChip: 'AI summary', placeholder: 'Describe your spreadsheet here...', clear: 'Clear text', language: 'Language', rows: 'Rows (approx.)',
    rowsHint: (m: number) => `Max ${m.toLocaleString('en-US')} rows`,
    create: 'Create Excel', creating: 'Creating…', tooShort: 'Enter at least 3 characters.', tooLong: (m: number) => `Maximum ${m} characters.`,
    retry: 'Try again', error: 'Could not create the file.',
    feats: [['Professional design', 'Modern interface and a smooth experience'], ['AI-powered', 'Runs on open language models'],
      ['Fast and efficient', 'From description to Excel in simple steps'], ['Safe and validated', 'Strict validation of inputs and formulas']],
    suggested: 'Suggested examples', resultTag: 'Sample result', exTitle: 'Monthly expenses sheet',
    exChecks: ['Professional formatting', 'Automatic formulas', 'Ready to print or edit'], exFile: 'Excel file ready to download',
    exCols: ['Date', 'Type', 'Description', 'Amount'], exTotal: 'Total',
    exRows: [['2025-10-01', 'Housing', 'House rent', '1200'], ['2025-10-03', 'Transport', 'Fuel', '150'], ['2025-10-07', 'Food', 'Groceries', '320'], ['2025-10-12', 'Leisure', 'Restaurant', '180']],
    resultTitle: 'Generation result',
    done: 'Your Excel file is ready', downloadBtn: 'Download file', cancel: 'Cancel', warnings: (n: number) => `${n} unsupported item(s) were skipped; details are in the "Summary" sheet inside the file.`,
    previewNote: (shown: number, total: number) => `Preview of the first ${shown.toLocaleString('en-US')} of ${total.toLocaleString('en-US')} rows. The file contains every row.`,
    colsNote: (shown: number, total: number) => `Showing ${shown} of ${total} columns.`, calcsTitle: 'Calculations included in the file',
    calcNote: 'Values are calculated when you open the file in Excel.', syntheticTag: 'Sample data', refId: 'Reference',
    retryIn: (s: number) => `You can try again in about ${s} seconds.`,
    errors: {
      invalid_request: 'Invalid request. Check the text and the row count.', payload_too_large: 'The request is too large. Shorten the description.', length_required: 'The request could not be sent. Refresh and try again.',
      invalid_spec: 'The request could not be understood or exceeds the allowed limits. Rephrase it, or reduce columns/rows.', rate_limited: 'Too many requests. Wait a moment and try again.',
      ai_quota: 'The free AI quota is temporarily exhausted. Please try again later.', ai_unavailable: 'The AI service is currently unavailable.', busy: 'The server is busy right now. Please try again in a moment.',
      timeout: 'The request took too long. Please try again (the server may be waking up from sleep).', internal_error: 'An unexpected server error occurred.',
      network: 'Could not reach the server. Check your connection and try again.', aborted: 'The request was cancelled.', unknown: 'Could not create the file.' },
    demoBanner: 'Demo mode (Phase 2): the data below is illustrative and no real file was generated. Real downloads are enabled once the backend is connected.',
    download: 'Download (not available yet)', demoTag: 'Demo data', rowsOf: (n: number) => `${n.toLocaleString('en-US')} rows`,
    page: 'Page', of: 'of', prev: 'Previous', next: 'Next', total: 'Total rows', previewTitle: 'Spreadsheet preview',
    cols: ['Name', 'Department', 'Salary', 'Status'], ph: 'Item', statuses: ['Active', 'Inactive'], depts: ['Admin', 'Sales', 'Tech'],
    footerBar: 'Turn your ideas into professional spreadsheets with the power of AI', footer: 'Work in progress. Free services have usage limits.'
  }
} as const
