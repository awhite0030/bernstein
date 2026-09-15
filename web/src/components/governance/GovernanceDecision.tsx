import { useState } from 'react';
import { ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';
import { Pill } from '@/lib/states';
import { formatUSD } from '@/lib/format';

export type DecisionRecord = {
  v: number;
  run_id: string;
  subject: string;
  action: string;
  verdict: string;
  inputs_hash: string;
  timestamp: number;
  context: Record<string, any>;
  journal_entry_hash: string;
};

export function GovernanceDecisionRow({ decision }: { decision: DecisionRecord }) {
  const [open, setOpen] = useState(false);

  const isBudget = decision.action === 'budget';
  const hasPolicy = decision.context?.policy_version !== undefined;

  return (
    <div className="border-b border-border-subtle last:border-0" data-decision-row={decision.inputs_hash}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center justify-between py-3 text-left hover:bg-surface-raised/50 focus:outline-none"
      >
        <div className="flex items-center gap-3">
          <ChevronRight
            className={clsx(
              'h-4 w-4 text-muted-foreground transition-transform duration-200',
              open && 'rotate-90'
            )}
          />
          <div className="flex items-center gap-2 font-mono text-body">
            <span className="text-foreground">{decision.subject}</span>
            <span className="text-muted-foreground">→</span>
            <span className="text-foreground">{decision.action}</span>
          </div>
        </div>
        <Pill kind={decision.verdict === 'allow' ? 'success' : 'danger'}>
          {decision.verdict}
        </Pill>
      </button>

      {open && (
        <div className="pb-4 pl-8 pr-4">
          <div className="rounded-md border border-border bg-surface p-3 font-mono text-body-sm">
            <div className="grid grid-cols-[200px_1fr] gap-y-2 gap-x-4">
              <div className="text-muted-foreground">subject</div>
              <div className="text-foreground">{decision.subject}</div>

              <div className="text-muted-foreground">action</div>
              <div className="text-foreground">{decision.action}</div>

              <div className="text-muted-foreground">verdict</div>
              <div className="text-foreground">{decision.verdict}</div>

              <div className="text-muted-foreground">inputs_hash</div>
              <div className="text-foreground">{decision.inputs_hash}</div>

              {isBudget && decision.verdict === 'refuse' && (
                <>
                  <div className="text-muted-foreground">cap_usd</div>
                  <div className="text-foreground">{formatUSD(decision.context.cap_usd)}</div>
                  <div className="text-muted-foreground">projected prior spend</div>
                  <div className="text-foreground">
                     {decision.context.prior_spend_usd !== undefined
                       ? formatUSD(decision.context.prior_spend_usd)
                       : formatUSD((decision.context.cap_usd || 0) - (decision.context.next_cost_usd || 0))}
                  </div>
                </>
              )}

              {!hasPolicy && !isBudget && (
                 <>
                  <div className="text-muted-foreground">policy</div>
                  <div className="text-muted-foreground italic font-medium">this decision names no policy version</div>
                 </>
              )}

              <div className="text-muted-foreground">journal_entry_hash</div>
              <div className="text-foreground flex flex-col">
                 {decision.journal_entry_hash ? (
                   <span>{decision.journal_entry_hash}</span>
                 ) : (
                   <span className="text-muted-foreground italic">none</span>
                 )}
                 <span className="text-muted-foreground mt-1 text-[10px]">
                   record is meaningless without it
                 </span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
