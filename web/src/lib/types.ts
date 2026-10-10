// The shapes the web app reads, as the control plane sends them. A run level is
// `GET /levels/runs/{id}` (ADR-0063); a snapshot and a change are `contracts/changes/v1`
// (ADR-0055). A field the server leaves out is absent, never null.

/** Everything drawn for one element, as tokens of the visual vocabulary (ADR-0059). */
export interface Glyph {
	subject: 'step' | 'run';
	outline: string;
	edge?: string;
	exactness_mark: string;
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
}

/** An RFC 9457 problem, as every refusal of the surface is answered. */
export interface Problem {
	status: number;
	title: string;
	detail: string;
}
