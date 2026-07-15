import {
  ButtonItem,
  DropdownItem,
  Focusable,
  Navigation,
  PanelSection,
  PanelSectionRow,
  TextField,
  staticClasses,
} from "@decky/ui";
import { callable, definePlugin, toaster } from "@decky/api";
import { useEffect, useState } from "react";
import { GiSpellBook } from "react-icons/gi";

interface BuildSection {
  title: string;
  items: string[];
}

interface BuildVariant {
  name: string;
  sections: BuildSection[];
}

interface Build {
  id: string;
  name: string;
  provider: string;
  source_url: string;
  notes: string;
  sections: BuildSection[];
  variants?: BuildVariant[];
  progress?: Record<string, boolean>;
  pinned: boolean;
  added_at: number;
}

const addBuild = callable<[url: string, notes: string], Build>("add_build");
const getBuilds = callable<[], Build[]>("get_builds");
const removeBuild = callable<[build_id: string], Build[]>("remove_build");
const togglePin = callable<[build_id: string], Build[]>("toggle_pin");
const refreshBuild = callable<[build_id: string], Build[]>("refresh_build");
const getSectionOrder = callable<[], string[]>("get_section_order");
const setSectionOrder = callable<[order: string[]], string[]>("set_section_order");
const setNotes = callable<[build_id: string, notes: string], Build[]>("set_notes");
const toggleStep = callable<[build_id: string, key: string], Build[]>("toggle_step");
const clearProgress = callable<[build_id: string, prefix: string], Build[]>(
  "clear_progress",
);

/** Sort sections by the user's preferred title order. Titles not in the
 * preference keep their natural relative order after the preferred ones
 * (sort is stable). An empty preference is a no-op. */
function applySectionOrder(
  sections: BuildSection[],
  order: string[],
): BuildSection[] {
  if (!order.length) return sections;
  const rank = new Map(order.map((t, i) => [t, i]));
  return [...sections].sort(
    (a, b) =>
      (rank.get(a.title) ?? order.length) - (rank.get(b.title) ?? order.length),
  );
}

const PROVIDER_LABELS: Record<string, string> = {
  mobalytics: "Mobalytics",
  maxroll: "Maxroll",
  d4builds: "d4builds.gg",
  web: "Web",
};

function openGuide(url: string) {
  Navigation.CloseSideMenus();
  Navigation.NavigateToExternalWeb(url);
}

function BuildDetail({
  build,
  onBack,
  onChanged,
  sectionOrder,
  onOrderChanged,
}: {
  build: Build;
  onBack: () => void;
  onChanged: (builds: Build[]) => void;
  sectionOrder: string[];
  onOrderChanged: (order: string[]) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [variantIdx, setVariantIdx] = useState(0);
  const [reordering, setReordering] = useState(false);
  const [editingNotes, setEditingNotes] = useState(false);
  const [notesDraft, setNotesDraft] = useState(build.notes);
  const [checklist, setChecklist] = useState(false);

  const run = async (action: () => Promise<Build[]>, thenBack = false) => {
    setBusy(true);
    try {
      onChanged(await action());
      if (thenBack) onBack();
    } finally {
      setBusy(false);
    }
  };

  // Guides ship several build variants (Starter / Endgame / Pushing...).
  // The selector picks which one's sections render below; builds without
  // variants keep their flat sections.
  const variants = build.variants ?? [];
  const hasVariants = variants.length > 1;
  const selected = Math.min(variantIdx, Math.max(variants.length - 1, 0));
  const sections = applySectionOrder(
    hasVariants ? variants[selected].sections : build.sections,
    sectionOrder,
  );

  // Reorder mode: selecting a section bumps it up one place. Deliberately
  // not drag-and-drop - this must work with controller focus navigation.
  // The saved order is the full materialized title list, so it holds
  // across variants and other builds (it's a global preference).
  const moveUp = async (index: number) => {
    if (index <= 0) return;
    const titles = sections.map((s) => s.title);
    [titles[index - 1], titles[index]] = [titles[index], titles[index - 1]];
    onOrderChanged(await setSectionOrder(titles));
  };

  // Checklist: progress keys are variant|section|row-index|row-text. The
  // text is included so a refreshed guide whose rows shifted doesn't show
  // stale checkmarks on the wrong lines - a changed row simply unchecks.
  const variantKey = hasVariants ? variants[selected].name : "";
  const progress = build.progress ?? {};
  const stepKey = (sectionTitle: string, i: number, item: string) =>
    `${variantKey}|${sectionTitle}|${i}|${item.trim()}`;
  const checkedCount = sections.reduce(
    (n, s) =>
      n + s.items.filter((it, i) => progress[stepKey(s.title, i, it)]).length,
    0,
  );

  return (
    <>
      <PanelSection title={build.name}>
        <PanelSectionRow>
          <ButtonItem layout="below" onClick={onBack}>
            ← Back to library
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            onClick={() => openGuide(build.source_url)}
            description={PROVIDER_LABELS[build.provider] ?? build.provider}
          >
            Open full guide
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => run(() => togglePin(build.id))}
          >
            {build.pinned ? "Unpin" : "Pin as current build"}
          </ButtonItem>
        </PanelSectionRow>
        {hasVariants && (
          <PanelSectionRow>
            <DropdownItem
              label="Variant"
              rgOptions={variants.map((v, i) => ({ data: i, label: v.name }))}
              selectedOption={selected}
              onChange={(option) => setVariantIdx(option.data as number)}
            />
          </PanelSectionRow>
        )}
        {sections.length > 1 && (
          <PanelSectionRow>
            <ButtonItem layout="below" onClick={() => setReordering(!reordering)}>
              {reordering ? "Done reordering" : "Reorder sections"}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {sections.length > 0 && (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              onClick={() => setChecklist(!checklist)}
              description={
                checkedCount > 0 ? `${checkedCount} steps checked` : undefined
              }
            >
              {checklist ? "Done checking" : "Checklist mode"}
            </ButtonItem>
          </PanelSectionRow>
        )}
        {checklist && checkedCount > 0 && (
          <PanelSectionRow>
            <ButtonItem
              layout="below"
              disabled={busy}
              onClick={() => run(() => clearProgress(build.id, `${variantKey}|`))}
            >
              Reset checks{hasVariants ? " (this variant)" : ""}
            </ButtonItem>
          </PanelSectionRow>
        )}
      </PanelSection>

      {reordering && (
        <PanelSection title="Section order">
          {sections.map((section, i) => (
            <PanelSectionRow key={section.title}>
              <ButtonItem
                layout="below"
                disabled={i === 0}
                onClick={() => moveUp(i)}
                description={i === 0 ? "Top" : "Select to move up"}
              >
                {`▲ ${section.title}`}
              </ButtonItem>
            </PanelSectionRow>
          ))}
        </PanelSection>
      )}

      {!reordering && sections.map((section) => {
        // Providers emit hierarchical sections (an item/skill header with
        // "  – " sub-rows). Leading whitespace collapses in HTML, so the
        // hierarchy must be restored with styling: headers bold, sub-rows
        // indented and dimmed. Flat sections keep the plain look.
        const hierarchical = section.items.some((it) => it.startsWith("  "));
        return (
          <PanelSection key={section.title} title={section.title}>
            {section.items.map((item, i) => {
              const sub = item.startsWith("  ");
              const key = stepKey(section.title, i, item);
              const done = !!progress[key];
              const text = (done ? "✓ " : checklist ? "○ " : "") + item.trim();
              const style = {
                fontSize: "0.9em",
                padding: "2px 0",
                paddingLeft: sub ? "14px" : 0,
                fontWeight: hierarchical && !sub ? 600 : 400,
                opacity: done ? 0.45 : sub ? 0.85 : 1,
                textDecoration: done ? "line-through" : undefined,
              } as const;
              return (
                <PanelSectionRow key={i}>
                  {checklist ? (
                    <Focusable
                      style={{ ...style, cursor: "pointer" }}
                      onActivate={() => run(() => toggleStep(build.id, key))}
                      onClick={() => run(() => toggleStep(build.id, key))}
                    >
                      {text}
                    </Focusable>
                  ) : (
                    <div style={style}>{text}</div>
                  )}
                </PanelSectionRow>
              );
            })}
          </PanelSection>
        );
      })}

      <PanelSection title="Notes">
        {editingNotes ? (
          <>
            <PanelSectionRow>
              <TextField
                label="Notes"
                value={notesDraft}
                onChange={(e) => setNotesDraft(e.target.value)}
              />
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                disabled={busy}
                onClick={() =>
                  run(() => setNotes(build.id, notesDraft)).then(() =>
                    setEditingNotes(false),
                  )
                }
              >
                Save notes
              </ButtonItem>
            </PanelSectionRow>
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                onClick={() => {
                  setNotesDraft(build.notes);
                  setEditingNotes(false);
                }}
              >
                Cancel
              </ButtonItem>
            </PanelSectionRow>
          </>
        ) : (
          <>
            {build.notes && (
              <PanelSectionRow>
                <div style={{ fontSize: "0.9em", whiteSpace: "pre-wrap" }}>
                  {build.notes}
                </div>
              </PanelSectionRow>
            )}
            <PanelSectionRow>
              <ButtonItem
                layout="below"
                onClick={() => {
                  setNotesDraft(build.notes);
                  setEditingNotes(true);
                }}
              >
                {build.notes ? "Edit notes" : "Add notes"}
              </ButtonItem>
            </PanelSectionRow>
          </>
        )}
      </PanelSection>

      <PanelSection title="Manage">
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => run(() => refreshBuild(build.id))}
            description="Re-fetch the guide title and data"
          >
            Refresh from source
          </ButtonItem>
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem
            layout="below"
            disabled={busy}
            onClick={() => run(() => removeBuild(build.id), true)}
          >
            Remove from library
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>
    </>
  );
}

function Content() {
  const [builds, setBuilds] = useState<Build[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [url, setUrl] = useState("");
  const [adding, setAdding] = useState(false);
  const [sectionOrder, setSectionOrderState] = useState<string[]>([]);
  const [backendDown, setBackendDown] = useState(false);

  useEffect(() => {
    // If the backend never loaded (import error, wrong Decky version),
    // every button dies silently - surface it instead.
    getBuilds()
      .then(setBuilds)
      .catch(() => setBackendDown(true));
    getSectionOrder().then(setSectionOrderState).catch(() => {});
  }, []);

  const selected = builds.find((b) => b.id === selectedId);
  if (selected) {
    return (
      <BuildDetail
        build={selected}
        onBack={() => setSelectedId(null)}
        onChanged={setBuilds}
        sectionOrder={sectionOrder}
        onOrderChanged={setSectionOrderState}
      />
    );
  }

  const onAdd = async () => {
    const link = url.trim();
    if (!link) {
      // Never fail silently: if the virtual keyboard didn't commit the
      // text, the user needs to know the field still looks empty.
      toaster.toast({
        title: "Grimoire",
        body: "The link field looks empty — type or paste a guide URL first",
      });
      return;
    }
    setAdding(true);
    try {
      const build = await addBuild(link, "");
      setBuilds(await getBuilds());
      setUrl("");
      toaster.toast({ title: "Grimoire", body: `Saved "${build.name}"` });
    } catch (e) {
      toaster.toast({
        title: "Grimoire",
        body: `Could not save: ${String(e).slice(0, 140)}`,
      });
    } finally {
      setAdding(false);
    }
  };

  return (
    <>
      {backendDown && (
        <PanelSection title="Backend not responding">
          <PanelSectionRow>
            <div style={{ fontSize: "0.9em" }}>
              Grimoire's backend didn't answer. Restart Decky Loader, and if
              it persists check the log at homebrew/logs/Grimoire on the
              Deck.
            </div>
          </PanelSectionRow>
        </PanelSection>
      )}
      <PanelSection title="Add a build">
        <PanelSectionRow>
          <TextField
            label="Guide link"
            description="Paste a Mobalytics, Maxroll or d4builds.gg URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onBlur={(e) => setUrl((e.target as HTMLInputElement).value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          {/* Enabled even when the field looks empty: on the Deck the
              virtual keyboard can commit text without firing onChange, and
              a dead disabled button gives the user zero feedback. */}
          <ButtonItem layout="below" disabled={adding} onClick={onAdd}>
            {adding ? "Saving…" : "Save to library"}
          </ButtonItem>
        </PanelSectionRow>
      </PanelSection>

      <PanelSection title="Library">
        {builds.length === 0 && (
          <PanelSectionRow>
            <div style={{ fontSize: "0.9em" }}>
              No builds yet. Paste a guide link above — it will be waiting here,
              one button press away, while you play.
            </div>
          </PanelSectionRow>
        )}
        {builds.map((b) => (
          <PanelSectionRow key={b.id}>
            <ButtonItem
              layout="below"
              onClick={() => setSelectedId(b.id)}
              description={PROVIDER_LABELS[b.provider] ?? b.provider}
            >
              {b.pinned ? `★ ${b.name}` : b.name}
            </ButtonItem>
          </PanelSectionRow>
        ))}
      </PanelSection>
    </>
  );
}

export default definePlugin(() => ({
  name: "Grimoire",
  titleView: <div className={staticClasses.Title}>Grimoire</div>,
  content: <Content />,
  icon: <GiSpellBook />,
}));
