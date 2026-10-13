import useConversationStore from "@/stores/useConversationStore";
import Action from "./Action";
import { ToolName } from "@/lib/tools/tools-handling";
export default function RecommendedActions() {
  const { recommendedActions } = useConversationStore();

  const formatName = (action: string) => {
    const formatted = action.replace(/_/g, " ");
    return formatted.charAt(0).toUpperCase() + formatted.slice(1);
  };

  return (
    <div className="flex gap-2">
      {recommendedActions.map((action) => (
        <Action
          key={action.name}
          functionName={action.name as ToolName}
          name={formatName(action.name)}
          parameters={action.parameters}
        />
      ))}
    </div>
  );
}
