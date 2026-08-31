import { ProfileMode } from '@/types/profile';
import useProfileStore from '@/store/useProfileStore';
import { useState } from 'react';

const MODE_LABELS: Record<ProfileMode, string> = {
  FIELD_AG: 'Field Ag',
  URBAN_GARDEN: 'Urban Garden',
};

const MODE_DESCRIPTIONS: Record<ProfileMode, string> = {
  FIELD_AG: 'Large-scale crop scanning, bulk recommendations, seasonal planning.',
  URBAN_GARDEN: 'Small-plot disease detection, micro-garden guidance, container advice.',
};

export default function ProfileSwitcher() {
  const { profileMode, setProfileMode } = useProfileStore();
  const [isSwitching, setIsSwitching] = useState(false);

  const handleToggle = async () => {
    setIsSwitching(true);
    try {
      const next: ProfileMode = profileMode === 'FIELD_AG' ? 'URBAN_GARDEN' : 'FIELD_AG';
      setProfileMode(next);
    } finally {
      setIsSwitching(false);
    }
  };

  const nextMode = profileMode === 'FIELD_AG' ? 'URBAN_GARDEN' : 'FIELD_AG';

  return (
    <div className="flex flex-col gap-3 p-4 rounded-2xl bg-slate-100 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 w-full">
      <div>
        <div className="flex items-center justify-between">
          <p className="text-xs font-bold uppercase tracking-wider text-emerald-800 dark:text-emerald-400">
            Context Mode
          </p>
          <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
            {MODE_LABELS[profileMode]}
          </span>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-300 mt-1 leading-relaxed">
          {MODE_DESCRIPTIONS[profileMode]}
        </p>
      </div>

      <div className="w-full">
        <button
          type="button"
          onClick={handleToggle}
          disabled={isSwitching}
          className="relative flex h-9 w-full items-center rounded-xl bg-slate-200 dark:bg-slate-900 p-1 transition-colors focus:outline-none focus:ring-2 focus:ring-emerald-500 disabled:opacity-60 cursor-pointer"
          aria-label={`Switch to ${MODE_LABELS[nextMode]} mode`}
        >
          <div
            className={`absolute top-1 bottom-1 w-[calc(50%-4px)] rounded-lg bg-emerald-600 shadow-sm transition-transform duration-200 ease-in-out ${
              profileMode === 'URBAN_GARDEN'
                ? 'translate-x-[calc(100%+4px)]'
                : 'translate-x-0'
            }`}
          />
          <div className="relative z-10 grid w-full grid-cols-2 text-center text-xs font-bold">
            <span
              className={`py-1 transition-colors ${
                profileMode === 'FIELD_AG'
                  ? 'text-white'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              Field Ag
            </span>
            <span
              className={`py-1 transition-colors ${
                profileMode === 'URBAN_GARDEN'
                  ? 'text-white'
                  : 'text-slate-600 dark:text-slate-400'
              }`}
            >
              Urban Garden
            </span>
          </div>
        </button>
      </div>
    </div>
  );
}
