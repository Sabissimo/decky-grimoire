import {
  ButtonItem,
  DropdownItem,
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
              return (
                <PanelSectionRow key={i}>
                  <div
                    style={{
                      fontSize: "0.9em",
                      padding: "2px 0",
                      paddingLeft: sub ? "14px" : 0,
                      fontWeight: hierarchical && !sub ? 600 : 400,
                      opacity: sub ? 0.85 : 1,
                    }}
                  >
                    {item.trim()}
                  </div>
                </PanelSectionRow>
              );
            })}
          </PanelSection>
        );
      })}

      {build.notes && (
        <PanelSection title="Notes">
          <PanelSectionRow>
            <div style={{ fontSize: "0.9em", whiteSpace: "pre-wrap" }}>
              {build.notes}
            </div>
          </PanelSectionRow>
        </PanelSection>
      )}

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

  useEffect(() => {
    getBuilds().then(setBuilds);
    getSectionOrder().then(setSectionOrderState);
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
    if (!url.trim()) return;
    setAdding(true);
    try {
      const build = await addBuild(url.trim(), "");
      setBuilds(await getBuilds());
      setUrl("");
      toaster.toast({ title: "Grimoire", body: `Saved "${build.name}"` });
    } catch (e) {
      toaster.toast({ title: "Grimoire", body: "Could not save that link" });
    } finally {
      setAdding(false);
    }
  };

  return (
    <>
      <PanelSection title="Add a build">
        <PanelSectionRow>
          <TextField
            label="Guide link"
            description="Paste a Mobalytics, Maxroll or d4builds.gg URL"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </PanelSectionRow>
        <PanelSectionRow>
          <ButtonItem layout="below" disabled={adding || !url.trim()} onClick={onAdd}>
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
