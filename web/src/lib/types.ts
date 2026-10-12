// The shapes the web app reads, as the control plane sends them. A run level is
// `GET /levels/runs/{id}` (ADR-0063); a snapshot and a change are `contracts/changes/v1`
// (ADR-0055). A field the server leaves out is absent, never null.

/** Everything drawn for one element, as tokens of the visual vocabulary (ADR-0059). */
export interface Glyph {
	subject: 'step' | 'run' | 'result' | 'source' | 'decision_request';
	membrane: string;
	nucleus: string;
	rings: string;
	fill: string;
	state_mark: string;
	motion: string;
	still_mark: string;
	text: string;
}

/** An element's glyph with motion allowed, and without. */
export interface Drawn {
	moving: Glyph;
	still: Glyph;
}

export interface Figure {
	name: string;
	value: number;
}

export interface Wait {
	account: string;
	cause: string;
	since: string;
	on?: string;
	role?: string;
	requests?: string[];
}

export interface StepElement {
	id: string;
	method: string;
	exactness?: string;
	state: string;
	depends_on?: string[];
	attempt: number;
	wait?: Wait;
	consumption?: Figure[];
	started_at?: string;
	finished_at?: string;
	/** The decision requests the step raised, with their status (ADR-0068). */
	decisions?: { id: string; status: string; drawn: Drawn; text: string }[];
	drawn: Drawn;
	text: string;
}

export interface RunElement {
	id: string;
	process_version: string;
	state: string;
	rehearsal: boolean;
	consumed?: Figure[];
	created_at: string;
	updated_at: string;
	drawn: Drawn;
	text: string;
}

export interface RunLevel {
	run: RunElement;
	steps: StepElement[];
	/** One sentence: how far the run is and what it does now. */
	summary: string;
}

export interface SnapshotRun {
	id: string;
	process_version: string;
	state: string;
	rehearsal?: boolean;
	steps?: { id: string; state: string; method: string }[];
}

export interface Snapshot {
	position: string | null;
	scope: { kind: 'tenant' | 'process' | 'run'; id?: string };
	runs?: SnapshotRun[];
}

export interface Change {
	position: string;
	run: string;
	step?: string;
	decision_request?: string;
	kind: string;
	outcome?: string;
	method?: string;
	recorded_at: string;
	rehearsal?: boolean;
	state: { run?: string; step?: string; decision_request?: string };
}

/** The autonomy statement of a process version (ADR-0026). */
export interface AutonomyStatement {
	level: number;
	reason: string;
	toward_next?: string;
	actions?: Record<string, { level: number; reason: string; toward_next?: string }>;
	history?: number;
}

export interface ProcessStepElement {
	id: string;
	method: string;
	exactness?: string;
	reason: string;
	rejected?: string[];
	fallback?: string;
	depends_on?: string[];
	/** The runs this step is running in right now; absent at rest. */
	running_in?: string[];
	drawn: Drawn;
	text: string;
}

export interface RunAtVersionElement {
	id: string;
	state: string;
	rehearsal: boolean;
	running?: string[];
	created_at: string;
	drawn: Drawn;
	text: string;
}

/** `GET /levels/processes/{id}` (ADR-0064). */
export interface ProcessLevel {
	process: {
		id: string;
		name: string;
		version: string;
		versions: { version: string; active?: boolean }[];
		autonomy: AutonomyStatement;
		autonomy_text: string;
		text: string;
	};
	steps: ProcessStepElement[];
	runs?: RunAtVersionElement[];
	/** One sentence: how its steps work, and how many run now. */
	summary: string;
}

export interface RunningStepElement {
	run: string;
	step: string;
	method: string;
	exactness?: string;
	drawn: Drawn;
	text: string;
}

/** A step of a process's active version, drawn on the overview among its process's cells. */
export interface CellElement {
	id: string;
	method: string;
	exactness?: string;
	depends_on?: string[];
	running_in?: string[];
	drawn: Drawn;
	text: string;
}

export interface ProcessSummaryElement {
	id: string;
	name: string;
	active_version?: string;
	autonomy_level?: number;
	/** How many of its runs work right now, by the run component's own definition. */
	working: number;
	/** How many of its runs wait right now, by the run component's own definition. */
	waiting: number;
	running?: RunningStepElement[];
	/** The steps of its active version, so that the overview draws every process as one body. */
	cells?: CellElement[];
	text: string;
}

/** `GET /levels/overview` (ADR-0067). */
export interface OverviewLevel {
	areas: {
		id: string;
		name: string;
		working: number;
		waiting: number;
		processes: ProcessSummaryElement[];
		text: string;
	}[];
	/** One sentence: how many steps work now and how, and how many runs wait. */
	summary: string;
}

/** `GET /levels/origins/{run}/{step}` (ADR-0068): the path back from a result. */
export interface OriginLevel {
	result: {
		id: string;
		run: string;
		step: string;
		exactness: string;
		digest?: string;
		outputs?: string[];
		depends_on: string[];
		drawn: Drawn;
		text: string;
	};
	steps: {
		id: string;
		run: string;
		step: string;
		process_version: string;
		method: string;
		exactness?: string;
		model?: string;
		adapter?: string;
		recorded_at: string;
		depends_on?: string[];
		drawn: Drawn;
		text: string;
	}[];
	sources?: {
		id: string;
		capability: string;
		ref: string;
		digest?: string;
		observed_at: string;
		drawn: Drawn;
		text: string;
	}[];
	/** One sentence: what produced the result, and which methods are on its path. */
	summary: string;
}

/** An RFC 9457 problem, as every refusal of the surface is answered. */
export interface Problem {
	status: number;
	title: string;
	detail: string;
}

/** One option of a decision request (ADR-0008). */
export interface DecisionOption {
	id: string;
	proposal: string;
	consequence?: string;
	effort?: string;
	recommended: boolean;
	reason?: string;
}

/** A decision request as its decider sees it: `GET /decisions` and `GET /decisions/{id}`
 * (ADR-0042). Who answered is shown to that person alone (ADR-0015). */
export interface AddressedRequest {
	id: string;
	decider: string;
	anchor?: string;
	raised_at: string;
	overdue: boolean;
	answered_by_you: boolean;
	reflection?: string;
	request: {
		id: string;
		raised_by: { run: string; step: string };
		class: string;
		situation: string;
		question: string;
		options: DecisionOption[];
		blocking: string[];
		due: string;
		status: 'open' | 'answered' | 'interpreted' | 'confirmed' | 'applied';
		answer_raw?: string;
		answer_interpreted?: { option: string; modifications?: string };
	};
}

/** `GET /decisions`. */
export interface AddressedList {
	identity: string;
	requests: AddressedRequest[];
	overdue: number;
}

/** A group's response times, or why they are withheld (ADR-0015). */
export interface ResponseAggregate {
	group: string;
	decisions?: number | null;
	median_seconds?: number | null;
	withheld?: string | null;
}

/** `GET /decisions/response-times`: the reader's own times, theirs alone, and the rest only
 * aggregated by role and department (ADR-0015, principle 14). */
export interface ResponseTimes {
	reader: string;
	own?: { request_id: string; run_id: string; seconds: number }[];
	own_total_seconds?: number | null;
	own_median_seconds?: number | null;
	by_role?: ResponseAggregate[];
	by_department?: ResponseAggregate[];
}
