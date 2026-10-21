import { Suspense } from "react";
import ConversationView from "./ConversationView";

// The id comes from the URL at request time; Suspense lets the static shell prerender.
export default function ConversationPage() {
  return (
    <Suspense>
      <ConversationView />
    </Suspense>
  );
}
