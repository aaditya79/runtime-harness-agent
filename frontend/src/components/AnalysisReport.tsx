import { ParsedReport, MarketConsensus, SimilarGame } from "@/types";
import { PredictionVisuals } from "./PredictionVisuals";
import { KeyFactors } from "./KeyFactors";
import { SimilarGames } from "./SimilarGames";
import { ReasoningCards } from "./ReasoningCards";
import { FinalVerdict } from "./FinalVerdict";
import { MarketDivergence } from "./MarketDivergence";
import { AgentBreakdown } from "./AgentBreakdown";
import { AgreementCards } from "./AgreementCards";

interface Props {
  report: ParsedReport;
  raw: any;
  homeTeam: string;
  awayTeam: string;
  consensus?: MarketConsensus;
  similar?: SimilarGame[];
  mode: string;
}

export function AnalysisReport({
  report,
  raw,
  homeTeam,
  awayTeam,
  consensus,
  similar,
  mode,
}: Props) {
  const isMulti = mode === "multi_agent";
  return (
    <div className="space-y-4">
      <PredictionVisuals report={report} homeTeam={homeTeam} awayTeam={awayTeam} />
      {consensus?.available && (
        <MarketDivergence
          report={report}
          consensus={consensus}
          homeTeam={homeTeam}
          awayTeam={awayTeam}
        />
      )}
      {report.key_factors && report.key_factors.length > 0 && (
        <KeyFactors factors={report.key_factors} />
      )}
      {similar && similar.length > 0 && <SimilarGames games={similar} />}
      {isMulti && raw?.agent_analyses && (
        <AgentBreakdown agents={raw.agent_analyses} />
      )}
      {isMulti && (
        <AgreementCards
          agreement={report.areas_of_agreement}
          disagreement={report.areas_of_disagreement}
        />
      )}
      <ReasoningCards
        reasoning={report.reasoning}
        valueAssessment={report.value_assessment}
      />
      <FinalVerdict report={report} homeTeam={homeTeam} awayTeam={awayTeam} />
    </div>
  );
}
